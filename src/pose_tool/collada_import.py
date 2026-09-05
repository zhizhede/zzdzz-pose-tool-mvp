"""Collada (.dae) 动作数据导入：Mixamo 导出的骨骼动画 → 单帧 pose.json。

只依赖标准库（xml.etree）。矩阵动画逐关节正向运动学求世界坐标，
再按观察者视角正交投影到画布（y 翻转 + 包围盒缩放居中）。
投影是有损的：2D pose 无法还原回 3D BVH/FBX，原始文件自行保留作出处。
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Any

from .schema import PoseFile

CANVAS_DEFAULT = 512
FIT_RATIO = 0.85
CONF = 0.9

# 归一化骨名 -> OpenPose-18 下标（mixamorig 实测命名）
_BONE_SLOT = {
    "head": 0,
    "neck": 1,
    "rightarm": 2, "rightforearm": 3, "righthand": 4,
    "leftarm": 5, "leftforearm": 6, "lefthand": 7,
    "rightupleg": 8, "rightleg": 9, "rightfoot": 10,
    "leftupleg": 11, "leftleg": 12, "leftfoot": 13,
}

# 4x4 矩阵，行主序（与 COLLADA 文件顺序一致），平移在 [12],[13],[14]


def _mat_mul(a: list[float], b: list[float]) -> list[float]:
    return [
        sum(a[i * 4 + k] * b[k * 4 + j] for k in range(4))
        for i in range(4)
        for j in range(4)
    ]


def _mat_translation(m: list[float]) -> tuple[float, float, float]:
    # 列向量约定：平移在第 4 列（下标 3 / 7 / 11），不是 12 / 13 / 14
    return m[3], m[7], m[11]


def _slot_for(bone_name: str) -> int | None:
    n = re.sub(r"^(mixamorig_|mixamorig:)", "", bone_name, flags=re.IGNORECASE)
    n = n.replace(":", "_").replace(" ", "").lower()
    if n in _BONE_SLOT:
        return _BONE_SLOT[n]
    # 通用回退：侧面 + 部位关键词（其他骨架命名习惯）
    side = None
    if "right" in n or n.startswith("r_"):
        side = "right"
    elif "left" in n or n.startswith("l_"):
        side = "left"
    if side:
        base = 8 if side == "right" else 11
        if "upleg" in n or "thigh" in n or "upperleg" in n:
            return base
        if "shin" in n or "calf" in n or "knee" in n or n.endswith("leg"):
            return base + 1
        if "foot" in n or "ankle" in n:
            return base + 2
    if "neck" in n:
        return 1
    if "head" in n and "top" not in n and "end" not in n:
        return 0
    return None


class _Bone:
    __slots__ = ("name", "parent", "static_matrix", "children")

    def __init__(self, name: str, parent: "_Bone | None", static_matrix: list[float]):
        self.name = name
        self.parent = parent
        self.static_matrix = static_matrix
        self.children: list[_Bone] = []


def _parse_floats(text: str | None) -> list[float]:
    if not text:
        return []
    return [float(v) for v in text.split()]


def _collect_bones(root: ET.Element) -> dict[str, _Bone]:
    bones: dict[str, _Bone] = {}

    def walk(node: ET.Element, parent: _Bone | None) -> None:
        name = node.get("name") or node.get("id") or ""
        static = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
        matrix_el = node.find(f"{_ns(root)}matrix")
        if matrix_el is not None and matrix_el.text:
            vals = _parse_floats(matrix_el.text)
            if len(vals) == 16:
                static = vals
        bone = _Bone(name, parent, static)
        if parent is not None:
            parent.children.append(bone)
        bones[name] = bone
        for child in node.findall(f"{_ns(root)}node"):
            walk(child, bone)

    ns = _ns(root)
    for scene in root.findall(f"{ns}library_visual_scenes/{ns}visual_scene"):
        for node in scene.findall(f"{ns}node"):
            walk(node, None)
    return bones


def _ns(root: ET.Element) -> str:
    if isinstance(root.tag, str) and root.tag.startswith("{"):
        return root.tag.split("}")[0] + "}"
    return ""


def _collect_animations(root: ET.Element) -> dict[str, tuple[list[float], list[float]]]:
    """{骨骼名: (关键帧时间数组, 16×N 展平矩阵数组)}"""
    ns = _ns(root)
    result: dict[str, tuple[list[float], list[float]]] = {}
    for anim in root.findall(f"{ns}library_animations/{ns}animation"):
        channel = anim.find(f"{ns}channel")
        if channel is None:
            continue
        target = channel.get("target", "")
        bone = target.split("/")[0].strip()
        sources: dict[str, list[float]] = {}
        sampler = anim.find(f"{ns}sampler")
        if sampler is None:
            continue
        for inp in sampler.findall(f"{ns}input"):
            semantic = inp.get("semantic")
            src_id = (inp.get("source") or "").lstrip("#")
            if semantic not in ("INPUT", "OUTPUT"):
                continue
            src = anim.find(f"{ns}source[@id='{src_id}']")
            if src is None:
                src = root.find(f"{ns}library_animations/{ns}animation/{ns}source[@id='{src_id}']")
            if src is None:
                continue
            vals = _parse_floats(src.find(f"{ns}float_array").text if src.find(f"{ns}float_array") is not None else None)
            sources[semantic] = vals
        if "INPUT" in sources and "OUTPUT" in sources:
            result[bone] = (sources["INPUT"], sources["OUTPUT"])
    return result


def _rot_part(m: list[float]) -> list[list[float]]:
    """世界矩阵的 3×3 旋转部分（行主序）。"""
    return [
        [m[0], m[4], m[8]],
        [m[1], m[5], m[9]],
        [m[2], m[6], m[10]],
    ]


def _mat_vec(r: list[list[float]], v: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        r[0][0] * v[0] + r[0][1] * v[1] + r[0][2] * v[2],
        r[1][0] * v[0] + r[1][1] * v[1] + r[1][2] * v[2],
        r[2][0] * v[0] + r[2][1] * v[1] + r[2][2] * v[2],
    )


def _transpose3(r: list[list[float]]) -> list[list[float]]:
    return [list(col) for col in zip(*r)]


def _bone_by_name(bones: dict[str, "_Bone"], normalized: str) -> "_Bone | None":
    for n, b in bones.items():
        stripped = re.sub(r"^(mixamorig_|mixamorig:)", "", n, flags=re.IGNORECASE)
        if stripped.replace(":", "_").replace(" ", "").lower() == normalized:
            return b
    return None


_FACING_AXIS_POOL = ("head", "neck", "hips")


def _forward_world(bones: dict[str, "_Bone"], world_matrix) -> tuple[float, float, float] | None:
    """按 bind 姿态自标定的"人物面朝方向"单位向量（世界系）。

    Mixamo bind 姿态角色面向世界 +Z：把 +Z 反算进骨骼 bind 局部系得到
    朝向前向量的局部坐标，再用当前帧世界旋转转回世界系。不依赖骨骼轴约定。
    """
    for axis_bone in _FACING_AXIS_POOL:
        bone = _bone_by_name(bones, axis_bone)
        if bone is None:
            continue
        r_bind = _rot_part(world_matrix(bone, use_anim=False))
        f_local = _mat_vec(_transpose3(r_bind), (0.0, 0.0, 1.0))
        n = math.sqrt(sum(v * v for v in f_local))
        if n < 1e-6:
            continue
        f_local = (f_local[0] / n, f_local[1] / n, f_local[2] / n)
        r_frame = _rot_part(world_matrix(bone, use_anim=True))
        f_world = _mat_vec(r_frame, f_local)
        n2 = math.sqrt(sum(v * v for v in f_world))
        if n2 < 1e-6:
            continue
        return (f_world[0] / n2, f_world[1] / n2, f_world[2] / n2)
    return None


_FACING_Z_EPS = 0.2  # 前向向量 z 分量超过该值判正/背，否则视为侧面（约 11.5°）


def _facing_for(bones: dict[str, "_Bone"], world_matrix) -> str | None:
    """判定当前帧人物朝向：front（面向观察者）/ back / profile / None。"""
    f_world = _forward_world(bones, world_matrix)
    if f_world is None:
        return None
    if f_world[2] > _FACING_Z_EPS:
        return "front"
    if f_world[2] < -_FACING_Z_EPS:
        return "back"
    return "profile"


# 面部点合成：COCO-18 的脸只有鼻(0)/双眼(14,15)/双耳(16,17) 五个标准点。
# Mixamo rig 没有面部骨骼，用头骨世界变换 + 头颈距离作比例单位摆放
# "虚拟眼骨"——相当于 MMD 的目/両目骨骼在任意 rig 上的等价物。
_FACE_OFFSETS = {
    0:  (0.55, 0.35, 0.00),   # nose：前方偏上
    14: (0.45, 0.50, 0.18),   # right_eye：人物自身右侧（正面像的图左侧）
    15: (0.45, 0.50, -0.18),  # left_eye
    16: (-0.05, 0.45, 0.50),  # right_ear：耳在矢状面，略靠后
    17: (-0.05, 0.45, -0.50), # left_ear
}
# 相对头骨中心的相机轴深度低于该值判被头颅遮挡（耳约 -0.05d 仍可见）
_FACE_VIS_EPS = -0.15


def _synth_face_points(bones: dict[str, "_Bone"], world_matrix, slots) -> bool:
    """合成 18 点标准面部五点（3D 世界坐标），随朝向自动显隐。"""
    head = _bone_by_name(bones, "head")
    neck = _bone_by_name(bones, "neck")
    if head is None or neck is None:
        return False
    f = _forward_world(bones, world_matrix)
    if f is None:
        return False
    hx, hy, hz = _mat_translation(world_matrix(head))
    nx, ny, nz = _mat_translation(world_matrix(neck))
    d = math.sqrt((hx - nx) ** 2 + (hy - ny) ** 2 + (hz - nz) ** 2)
    if d < 1e-6:
        return False
    # 人物右方 = forward × up（f=+Z 时为 -X，即正面像里右眼落在图左侧，符合 COCO 约定）
    rx, ry, rz = f[1] * 0.0 - f[2] * 1.0, f[2] * 0.0 - f[0] * 0.0, f[0] * 1.0 - f[1] * 0.0
    rlen = math.sqrt(rx * rx + ry * ry + rz * rz)
    if rlen < 1e-6:
        return False
    rx, ry, rz = rx / rlen, ry / rlen, rz / rlen
    for slot, (a_fwd, b_up, c_right) in _FACE_OFFSETS.items():
        px = hx + f[0] * a_fwd * d + rx * c_right * d
        py = hy + f[1] * a_fwd * d + 1.0 * b_up * d + ry * c_right * d
        pz = hz + f[2] * a_fwd * d + rz * c_right * d
        visible = (pz - hz) > _FACE_VIS_EPS * d
        slots[slot] = (px, py, pz, CONF if visible else 0.0)  # type: ignore[misc]
    return True


def parse_collada(
    source: bytes | str | Path,
    frame: int = 0,
    canvas: int = CANVAS_DEFAULT,
    projection: str = "real",
) -> tuple[PoseFile, list[str], int]:
    """解析 Collada 骨骼动画，返回 (pose, warnings, 总关键帧数)。

    projection="real"：真实比例投影——画布高度固定对应 190cm 世界身高，
    脚底锚定画布底边。保留"臀部低=坐姿"的高度线索（包围盒归一化会抹掉它，
    导致坐姿在 2D 上读起来像站立）。
    projection="fit"：旧版包围盒适配。
    """
    if isinstance(source, (bytes, bytearray)):
        root = ET.parse(BytesIO(source)).getroot()
    elif isinstance(source, str) and source.lstrip().startswith("<"):
        root = ET.fromstring(source)
    else:
        root = ET.parse(Path(source)).getroot()

    warnings: list[str] = []
    bones = _collect_bones(root)
    animations = _collect_animations(root)
    if not bones:
        raise ValueError("Collada 中未找到骨骼节点（library_visual_scenes 为空）")
    if not animations:
        raise ValueError("Collada 中未找到骨骼动画（library_animations 为空）")

    total_frames = max(len(t) for t, _ in animations.values())
    idx = frame if frame >= 0 else total_frames + frame
    if idx >= total_frames or idx < 0:
        raise ValueError(
            f"帧号 {frame} 越界：该动画共 {total_frames} 关键帧（0~{total_frames - 1}）"
        )

    slots: list[tuple[float, float, float, float]] = [(0.0, 0.0, 0.0, 0.0)] * 18
    mapped: set[int] = set()

    def world_matrix(bone: _Bone, use_anim: bool = True) -> list[float]:
        m = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
        chain: list[_Bone] = []
        cur: _Bone | None = bone
        while cur is not None:
            chain.append(cur)
            cur = cur.parent
        for b in reversed(chain):
            local = None
            if use_anim:
                anim = animations.get(b.name)
                if anim is not None:
                    times, values = anim
                    if idx * 16 + 16 <= len(values):
                        local = values[idx * 16: idx * 16 + 16]
            if local is None:
                local = b.static_matrix
            m = _mat_mul(m, local)
        return m

    def world_position(bone: _Bone) -> tuple[float, float, float]:
        return _mat_translation(world_matrix(bone))

    for name, bone in bones.items():
        slot = _slot_for(name)
        if slot is None or slot in mapped:
            continue
        x, y, z = world_position(bone)
        slots[slot] = (x, y, z, CONF)  # type: ignore[misc]
        mapped.add(slot)

    # 朝向判定：bind 姿态自标定面朝方向（Mixamo bind 面向 +Z），不依赖骨骼轴约定
    facing = _facing_for(bones, world_matrix)
    # 面部五点合成（虚拟眼骨）：正面显示鼻+双眼+双耳，背面只留耳廓
    synth_ok = _synth_face_points(bones, world_matrix, slots)

    missing = [
        i for i in range(18)
        if i not in mapped and not (synth_ok and i in _FACE_OFFSETS)
    ]
    if missing:
        warnings.append(f"未映射到骨骼的标准点：{missing}（导入后为隐藏点，可在编辑器补）")

    # 投影：y-up 世界 → 画布（y 翻转）
    mapped_pts = [(x, y) for x, y, _z, c in slots if c > 0]
    if not mapped_pts:
        raise ValueError("骨骼动画存在但没有任何点映射成功")

    if projection == "real":
        xs = [p[0] for p in mapped_pts]
        ys = [p[1] for p in mapped_pts]
        h_world = max(ys) - min(ys)
        w_world = max(xs) - min(xs)
        ground = min(ys)
        cx = (max(xs) + min(xs)) / 2
        # 画布高度固定对应 190cm 世界身高；超宽/超高姿势按比例收缩
        s = canvas / 190.0
        if h_world > 0:
            s = min(s, canvas * 0.98 / h_world)
        if w_world > 0:
            s = min(s, canvas * 0.92 / w_world)
        for i, (x, y, _z, c) in enumerate(slots):
            if c <= 0:
                continue
            px = canvas / 2 + (x - cx) * s
            py = canvas - (y - ground) * s
            slots[i] = (round(min(max(px, 0.0), canvas - 1.0), 1),
                        round(min(max(py, 0.0), canvas - 1.0), 1), 0.0, c)  # type: ignore[misc]
        warnings.append("真实比例投影：坐姿/蹲姿人物会明显偏矮，属预期（保留高度线索）")
    else:
        # 旧包围盒适配
        xs = [p[0] for p in mapped_pts]
        ys = [p[1] for p in mapped_pts]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        scale = min(canvas * 0.85 / w, canvas * 0.85 / h) if w > 0 and h > 0 else 1.0
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        for i, (x, y, _z, c) in enumerate(slots):
            if c <= 0:
                continue
            slots[i] = (round((x - cx) * scale + canvas / 2, 1),
                        round(canvas / 2 - (y - cy) * scale, 1), 0.0, c)  # type: ignore[misc]

    flat: list[float] = []
    for x, y, _z, c in slots:
        flat.extend([float(x), float(y), float(c)])

    person: dict[str, Any] = {"pose_keypoints_2d": flat}
    if facing:
        person["facing"] = facing
    pose = PoseFile.model_validate({
        "version": "0.2",
        "canvas_width": canvas,
        "canvas_height": canvas,
        "meta": {"source_format": "collada", "source_frame": idx},
        "people": [person],
    })
    warnings.insert(0, f"该动画共 {total_frames} 关键帧，当前导入第 {idx} 帧（可换帧获得其他姿势）")
    if facing:
        warnings.append(
            f"3D 朝向判定：{facing}"
            + ("（鼻/眼点已隐藏，生成时提示词建议加 back view）" if facing == "back" else "")
        )
    warnings.append("左右为观察者视角约定，导入后请目视核对方向")
    return pose, warnings, total_frames

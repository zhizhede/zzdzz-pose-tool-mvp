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

    def world_position(bone: _Bone) -> tuple[float, float, float]:
        m = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
        chain: list[_Bone] = []
        cur: _Bone | None = bone
        while cur is not None:
            chain.append(cur)
            cur = cur.parent
        for b in reversed(chain):
            anim = animations.get(b.name)
            local = None
            if anim is not None:
                times, values = anim
                if idx * 16 + 16 <= len(values):
                    local = values[idx * 16: idx * 16 + 16]
            if local is None:
                local = b.static_matrix
            m = _mat_mul(m, local)
        return _mat_translation(m)

    for name, bone in bones.items():
        slot = _slot_for(name)
        if slot is None or slot in mapped:
            continue
        x, y, z = world_position(bone)
        slots[slot] = (x, y, z, CONF)  # type: ignore[misc]
        mapped.add(slot)

    missing = [i for i in range(18) if i not in mapped]
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

    pose = PoseFile.model_validate({
        "version": "0.2",
        "canvas_width": canvas,
        "canvas_height": canvas,
        "meta": {"source_format": "collada", "source_frame": idx},
        "people": [{"pose_keypoints_2d": flat}],
    })
    warnings.insert(0, f"该动画共 {total_frames} 关键帧，当前导入第 {idx} 帧（可换帧获得其他姿势）")
    warnings.append("左右为观察者视角约定，导入后请目视核对方向")
    return pose, warnings, total_frames

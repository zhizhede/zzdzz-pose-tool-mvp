"""pose.json → BVH（Biovision 层级格式）导出。

用途：把 18 点 3D 关节真值转成 Blender / Unity / 多数 3D 软件可直接导入的
骨架姿势数据（单帧 BVH）。

设计说明：单帧姿势的"位置→旋转"转换在多子关节处是过约束问题，稳健做法是
**rest 骨架即姿势**——OFFSET 直接取本帧实际段向量（父关节→本关节），
MOTION 旋转通道全 0。导入 3D 软件后得到的就是摆好姿势的骨架，
关节世界位置与 pose_keypoints_3d 逐点一致（tests/test_bvh.py 有 FK 往返校验）。

坐标系与 pose_keypoints_3d 一致（y-up，单位与 rig 相同，Mixamo 为厘米）。
Blender 导入时选 Y-up 轴向预设。
"""

from __future__ import annotations

import math
from pathlib import Path

from .schema import PoseFile

# 骨架拓扑：(关节名, 父关节)。rest 骨架即姿势本身，无 rest 方向概念。
_SKELETON = [
    ("Hips", None),
    ("Spine", "Hips"),
    ("Neck", "Spine"),
    ("Head", "Neck"),
    ("HeadTip", "Head"),
    ("RightShoulder", "Neck"),
    ("RightArm", "RightShoulder"),
    ("RightHand", "RightArm"),
    ("RightHandTip", "RightHand"),
    ("LeftShoulder", "Neck"),
    ("LeftArm", "LeftShoulder"),
    ("LeftHand", "LeftArm"),
    ("LeftHandTip", "LeftHand"),
    ("RightUpLeg", "Hips"),
    ("RightLeg", "RightUpLeg"),
    ("RightFoot", "RightLeg"),
    ("RightToeBase", "RightFoot"),
    ("LeftUpLeg", "Hips"),
    ("LeftLeg", "LeftUpLeg"),
    ("LeftFoot", "LeftLeg"),
    ("LeftToeBase", "LeftFoot"),
]

NOSE, NECK = 0, 1
R_SHO, R_ELB, R_WRI, L_SHO, L_ELB, L_WRI = 2, 3, 4, 5, 6, 7
R_HIP, R_KNEE, R_ANK, L_HIP, L_KNEE, L_ANK = 8, 9, 10, 11, 12, 13


def _extend(joint, target, scale):
    v = (target[0] - joint[0], target[1] - joint[1], target[2] - joint[2])
    return (joint[0] + v[0] * scale, joint[1] + v[1] * scale, joint[2] + v[2] * scale)


def _joint_positions(person) -> dict[str, tuple[float, float, float]]:
    """pose_keypoints_3d → 骨架关节世界坐标（含合成关节）。"""
    raw = person.pose_keypoints_3d
    p = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    hips = ((p[R_HIP][0] + p[L_HIP][0]) / 2, (p[R_HIP][1] + p[L_HIP][1]) / 2,
            (p[R_HIP][2] + p[L_HIP][2]) / 2)
    # 头关节：双耳中点比鼻尖稳（鼻尖朝前会造成假俯仰）；无耳退化为鼻
    if math.dist(p[16], (0, 0, 0)) > 0 and math.dist(p[17], (0, 0, 0)) > 0:
        head = ((p[16][0] + p[17][0]) / 2, (p[16][1] + p[17][1]) / 2, (p[16][2] + p[17][2]) / 2)
    else:
        head = p[NOSE]
    return {
        "Hips": hips,
        "Spine": hips,                        # 与 Hips 重合：骨骼方向由 Neck 决定
        "Neck": p[NECK],
        "Head": head,
        "HeadTip": _extend(head, p[NOSE], 2.2),
        "RightShoulder": p[R_SHO],
        "RightArm": p[R_ELB],
        "RightHand": p[R_WRI],
        "RightHandTip": _extend(p[R_WRI], p[R_ELB], -0.35),
        "LeftShoulder": p[L_SHO],
        "LeftArm": p[L_ELB],
        "LeftHand": p[L_WRI],
        "LeftHandTip": _extend(p[L_WRI], p[L_ELB], -0.35),
        "RightUpLeg": p[R_HIP],
        "RightLeg": p[R_KNEE],
        "RightFoot": p[R_ANK],
        "RightToeBase": _extend(p[R_ANK], p[R_KNEE], -0.5),
        "LeftUpLeg": p[L_HIP],
        "LeftLeg": p[L_KNEE],
        "LeftFoot": p[L_ANK],
        "LeftToeBase": _extend(p[L_ANK], p[L_KNEE], -0.5),
    }


def export_bvh(pose: PoseFile, person_index: int = 0, frame_time: float = 0.033333) -> str:
    """导出单帧 BVH 文本。person 需携带 pose_keypoints_3d。"""
    person = pose.people[person_index]
    if not person.pose_keypoints_3d:
        raise ValueError("该姿态没有 pose_keypoints_3d（仅 DAE 导入的资产携带），无法导出 BVH")
    joints = _joint_positions(person)
    parent_of = {name: par for name, par in _SKELETON}
    children: dict[str, list[str]] = {}
    for name, par in _SKELETON:
        children.setdefault(par or "", []).append(name)

    def offset_vec(name: str) -> tuple[float, float, float]:
        par = parent_of[name]
        if par is None:
            return (0.0, 0.0, 0.0)
        j, pj = joints[name], joints[par]
        return (j[0] - pj[0], j[1] - pj[1], j[2] - pj[2])

    lines: list[str] = ["HIERARCHY"]

    def walk(name: str, indent: int):
        pad = "  " * indent
        lines.append(f"{pad}ROOT {name}" if parent_of[name] is None else f"{pad}JOINT {name}")
        lines.append(f"{pad}{{")
        v = offset_vec(name)
        lines.append(f"{pad}  OFFSET %.4f %.4f %.4f" % v)
        if parent_of[name] is None:
            lines.append(f"{pad}  CHANNELS 6 Xposition Yposition Zposition "
                         "Zrotation Xrotation Yrotation")
        else:
            lines.append(f"{pad}  CHANNELS 3 Zrotation Xrotation Yrotation")
        for child in children.get(name, []):
            walk(child, indent + 1)
        if name not in children:
            lines.append(f"{pad}  End Site")
            lines.append(f"{pad}  {{")
            tip = joints[name]
            lines.append(f"{pad}    OFFSET %.4f %.4f %.4f" % (tip[0] * 0.02, tip[1] * 0.02, tip[2] * 0.02))
            lines.append(f"{pad}  }}")
        lines.append(f"{pad}}}")

    walk("Hips", 0)

    # MOTION：rest 即姿势 → 旋转通道全 0，根位置 = 髋中心
    zero3 = "0.0000 0.0000 0.0000"
    frame_parts = ["%.4f %.4f %.4f" % joints["Hips"]]
    for name, _ in _SKELETON:
        frame_parts.append(zero3)

    lines.append("MOTION")
    lines.append("Frames: 1")
    lines.append(f"Frame Time: {frame_time:.6f}")
    lines.append(" ".join(frame_parts))
    return "\n".join(lines) + "\n"


def export_bvh_to_file(pose: PoseFile, output: str | Path, person_index: int = 0) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(export_bvh(pose, person_index=person_index), encoding="utf-8")
    return output

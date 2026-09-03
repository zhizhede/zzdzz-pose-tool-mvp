"""从 pose.json 关键点推导关节角度（骨骼角度）。

角度定义：关节处相邻两个肢段的夹角，0° 为完全折叠，180° 为肢段拉直。
只输出参与关键点全部可见（conf > 0）的角度。
"""

from __future__ import annotations

import math
from typing import Optional

from .schema import PoseFile

# 关节名 -> (近端关键点, 关节点, 远端关键点) 的 COCO-18 下标
_JOINTS = {
    "right_elbow": (2, 3, 4),
    "left_elbow": (5, 6, 7),
    "right_shoulder": (8, 2, 3),
    "left_shoulder": (11, 5, 6),
    "right_hip": (2, 8, 9),
    "left_hip": (5, 11, 12),
    "right_knee": (8, 9, 10),
    "left_knee": (11, 12, 13),
}

_JOINT_LABELS = {
    "right_elbow": "右肘",
    "left_elbow": "左肘",
    "right_shoulder": "右肩",
    "left_shoulder": "左肩",
    "right_hip": "右髋",
    "left_hip": "左髋",
    "right_knee": "右膝",
    "left_knee": "左膝",
    "torso_tilt_deg": "躯干倾角（相对竖直）",
    "head_tilt_deg": "头部倾斜（相对竖直方向）",
}


def _angle_deg(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    """b 为顶点的夹角 ∠abc，单位度，范围 [0, 180]。"""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        raise ValueError("关键点重合，无法计算角度")
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def compute_joint_angles(pose: PoseFile, person_index: int = 0) -> dict[str, Optional[float]]:
    person = pose.people[person_index]
    kps = person.keypoints("pose_keypoints_2d")

    def pt(i: int) -> tuple[float, float, float]:
        return kps[i]

    result: dict[str, Optional[float]] = {}
    for name, (i, j, k) in _JOINTS.items():
        if pt(i)[2] <= 0 or pt(j)[2] <= 0 or pt(k)[2] <= 0:
            result[name] = None
            continue
        result[name] = round(_angle_deg(pt(i)[:2], pt(j)[:2], pt(k)[:2]), 1)

    # 躯干倾角：双髋中点 → neck 相对竖直方向的偏角（0° 站立，90° 水平躺卧）
    neck = pt(1)
    l_hip, r_hip = pt(11), pt(8)
    if neck[2] > 0 and l_hip[2] > 0 and r_hip[2] > 0:
        mid_x = (l_hip[0] + r_hip[0]) / 2
        mid_y = (l_hip[1] + r_hip[1]) / 2
        result["torso_tilt_deg"] = round(_angle_deg(
            (mid_x, mid_y - 100), (mid_x, mid_y), neck[:2]
        ), 1)
    else:
        result["torso_tilt_deg"] = None

    # 头部倾斜：neck→nose 相对竖直向上方向的偏角
    nose, neck = pt(0), pt(1)
    if nose[2] > 0 and neck[2] > 0:
        result["head_tilt_deg"] = round(_angle_deg(
            (nose[0], nose[1] - 100), (neck[0], neck[1]), nose[:2]
        ), 1)
    else:
        result["head_tilt_deg"] = None
    return result


def format_angles(angles: dict[str, Optional[float]]) -> str:
    lines = []
    for name, value in angles.items():
        label = _JOINT_LABELS.get(name, name)
        lines.append(f"  {label}: {'—（关键点不可见）' if value is None else f'{value:.1f}°'}")
    return "\n".join(lines)

"""两个姿态之间的语义 diff：输出人可读的变化描述，而不是浮点噪音。"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .schema import N_BODY_KEYPOINTS, PoseFile


def person_keypoints(pose: PoseFile, person_index: int = 0) -> np.ndarray:
    data = np.asarray(pose.people[person_index].pose_keypoints_2d, dtype=float)
    return data.reshape(N_BODY_KEYPOINTS, 3)


def _derived_features(kps: np.ndarray) -> dict[str, float]:
    """从关键点推导的高层姿态特征，diff 时对比这些而不是逐像素。"""
    nose, neck = kps[0], kps[1]
    l_shoulder, r_shoulder = kps[5], kps[2]
    l_wrist, r_wrist = kps[7], kps[4]
    shoulder_width = max(abs(r_shoulder[0] - l_shoulder[0]), 1.0)
    return {
        # 越大表示头垂得越低
        "head_down_ratio": float((nose[1] - neck[1]) / shoulder_width),
        "shoulder_tilt_deg": float(
            math.degrees(math.atan2(r_shoulder[1] - l_shoulder[1], r_shoulder[0] - l_shoulder[0]))
        ),
        "hands_gap_px": float(math.hypot(r_wrist[0] - l_wrist[0], r_wrist[1] - l_wrist[1])),
    }


DERIVED_FEATURE_LABELS = {
    "head_down_ratio": "低头程度（nose 相对 neck 下移量 / 肩宽）",
    "shoulder_tilt_deg": "肩部倾斜角（度）",
    "hands_gap_px": "两手腕间距（px）",
}


def diff_poses(
    pose_a: PoseFile,
    pose_b: PoseFile,
    threshold_px: float = 2.0,
    person_index: int = 0,
) -> dict[str, Any]:
    if (pose_a.canvas_width, pose_a.canvas_height) != (pose_b.canvas_width, pose_b.canvas_height):
        raise ValueError("两个姿态的画布尺寸不同，坐标不可直接比较")

    ka = person_keypoints(pose_a, person_index)
    kb = person_keypoints(pose_b, person_index)

    moved = []
    for i in range(N_BODY_KEYPOINTS):
        dx = float(kb[i, 0] - ka[i, 0])
        dy = float(kb[i, 1] - ka[i, 1])
        if math.hypot(dx, dy) >= threshold_px:
            moved.append({
                "keypoint": i,
                "from": [float(ka[i, 0]), float(ka[i, 1])],
                "to": [float(kb[i, 0]), float(kb[i, 1])],
                "dx": dx,
                "dy": dy,
            })

    fa, fb = _derived_features(ka), _derived_features(kb)
    derived = {
        key: {"before": fa[key], "after": fb[key], "delta": fb[key] - fa[key]}
        for key in fa
    }
    return {
        "moved_keypoints": moved,
        "derived_features": derived,
        "summary": {"moved_count": len(moved), "total_keypoints": N_BODY_KEYPOINTS},
    }


def format_report(report: dict[str, Any]) -> str:
    from .schema import BODY_KEYPOINT_NAMES

    lines = []
    summary = report["summary"]
    lines.append(f"关键点变化：{summary['moved_count']}/{summary['total_keypoints']} 个移动（小于阈值的已忽略）")

    for m in report["moved_keypoints"]:
        name = BODY_KEYPOINT_NAMES[m["keypoint"]]
        directions = []
        if abs(m["dy"]) >= 1e-9:
            directions.append("下移" if m["dy"] > 0 else "上移")
        if abs(m["dx"]) >= 1e-9:
            directions.append("右移" if m["dx"] > 0 else "左移")
        dist = math.hypot(m["dx"], m["dy"])
        lines.append(
            f"  {name}: {'、'.join(directions) or '原位'} {dist:.1f}px"
            f"  ({m['from']} → {m['to']})"
        )

    lines.append("派生特征：")
    for key, label in DERIVED_FEATURE_LABELS.items():
        d = report["derived_features"][key]
        lines.append(f"  {label}: {d['before']:.3f} → {d['after']:.3f} (Δ{d['delta']:+.3f})")
    return "\n".join(lines)

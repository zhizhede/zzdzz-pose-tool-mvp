
import math
from pathlib import Path

import pytest

from pose_tool.angles import compute_joint_angles, format_angles
from pose_tool.schema import PoseFile

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "poses" / "looking-down-phone" / "pose.json"


def _pose_from(keypoints: list[float]) -> PoseFile:
    return PoseFile.model_validate({
        "canvas_width": 512,
        "canvas_height": 512,
        "people": [{"pose_keypoints_2d": keypoints}],
    })


def test_tpose_straight_arms():
    """T-pose：手臂水平伸直，肘部应接近 180°，肩部接近 90°。"""

    kps = []
    # 0 nose, 1 neck, 2 r_shoulder, 3 r_elbow, 4 r_wrist,
    # 5 l_shoulder, 6 l_elbow, 7 l_wrist, 8/9/10 右腿, 11/12/13 左腿,
    # 14-17 眼耳
    coords = [
        (256, 100), (256, 200), (356, 200), (456, 200), (556, 200),
        (156, 200), (56, 200), (-44, 200), (356, 300), (356, 400), (356, 500),
        (156, 300), (156, 400), (156, 500),
        (246, 90), (266, 90), (276, 100), (236, 100),
    ]
    for x, y in coords:
        kps.extend([x, y, 0.9])
    angles = compute_joint_angles(_pose_from(kps))
    assert abs(angles["right_elbow"] - 180.0) < 1.0
    assert abs(angles["left_elbow"] - 180.0) < 1.0
    assert abs(angles["right_shoulder"] - 90.0) < 1.0
    assert abs(angles["head_tilt_deg"]) < 30.0


def test_bent_elbow_less_than_90():
    """低头看手机样例：右臂大弯折，右肘应明显小于 90°。"""
    pose = PoseFile.model_validate({
        "canvas_width": 512,
        "canvas_height": 512,
        "people": [{"pose_keypoints_2d": [
            256, 180, 0.95, 256, 235, 0.96, 317, 235, 0.96, 340, 280, 0.94,
            268, 345, 0.9, 195, 235, 0.96, 180, 300, 0.92, 248, 340, 0.9,
            292, 360, 0.94, 297, 440, 0.92, 302, 500, 0.9, 220, 360, 0.94,
            215, 440, 0.92, 210, 500, 0.9, 264, 175, 0.93, 248, 175, 0.93,
            280, 178, 0.85, 232, 178, 0.85,
        ]}],
    })
    angles = compute_joint_angles(pose)
    assert angles["right_elbow"] == pytest.approx(105.0, abs=1.0)
    assert angles["left_elbow"] == pytest.approx(107.5, abs=1.5)


def test_invisible_keypoint_yields_none():
    pose = PoseFile.model_validate({
        "canvas_width": 512,
        "canvas_height": 512,
        "people": [{"pose_keypoints_2d": [
            256, 180, 0.95, 256, 235, 0.96, 317, 235, 0.96, 0, 0, 0.0,
            0, 0, 0.0, 195, 235, 0.96, 180, 300, 0.92, 248, 340, 0.9,
            0, 0, 0.0, 0, 0, 0.0, 0, 0, 0.0, 0, 0, 0.0,
            0, 0, 0.0, 0, 0, 0.0, 264, 175, 0.93, 248, 175, 0.93,
            280, 178, 0.85, 232, 178, 0.85,
        ]}],
    })
    angles = compute_joint_angles(pose)
    assert angles["right_elbow"] is None
    assert angles["left_elbow"] is not None


def test_format_angles_handles_none():
    pose = PoseFile.model_validate({
        "canvas_width": 512,
        "canvas_height": 512,
        "people": [{"pose_keypoints_2d": [float(i) for i in range(54)]}],
    })
    text = format_angles(compute_joint_angles(pose))
    assert "右肘" in text

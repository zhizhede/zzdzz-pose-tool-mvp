import math
from pathlib import Path

import pytest

from pose_tool.diff import diff_poses, format_report
from pose_tool.schema import load_pose

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "poses" / "looking-down-phone" / "pose.json"


def _head_down_variant():
    pose = load_pose(SAMPLE)
    changed = pose.model_copy(deep=True)
    changed.people[0].pose_keypoints_2d[1] += 40.0  # nose.y 下移 40px
    return pose, changed


def test_diff_detects_moved_keypoint():
    a, b = _head_down_variant()
    report = diff_poses(a, b)
    moved = {m["keypoint"] for m in report["moved_keypoints"]}
    assert moved == {0}  # 只有 nose 动了
    nose = report["moved_keypoints"][0]
    assert nose["dy"] == 40.0
    assert nose["dx"] == 0.0


def test_diff_derived_head_down_ratio_increases():
    a, b = _head_down_variant()
    report = diff_poses(a, b)
    assert report["derived_features"]["head_down_ratio"]["delta"] > 0


def test_diff_threshold_filters_tiny_changes():
    a = load_pose(SAMPLE)
    b = a.model_copy(deep=True)
    b.people[0].pose_keypoints_2d[1] += 1.0  # 1px < 默认阈值 2px
    report = diff_poses(a, b)
    assert report["summary"]["moved_count"] == 0


def test_diff_rejects_different_canvas():
    a = load_pose(SAMPLE)
    b = a.model_copy(deep=True)
    b.canvas_height = 256
    with pytest.raises(ValueError):
        diff_poses(a, b)


def test_format_report_is_human_readable():
    a, b = _head_down_variant()
    text = format_report(diff_poses(a, b))
    assert "nose" in text
    assert "低头程度" in text

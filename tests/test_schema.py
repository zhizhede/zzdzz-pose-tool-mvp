import io
from pathlib import Path

import pytest
from pydantic import ValidationError

from pose_tool.schema import PoseFile, export_json_schema, load_pose

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "poses" / "looking-down-phone" / "pose.json"

VALID = {
    "canvas_width": 512,
    "canvas_height": 512,
    "people": [{"pose_keypoints_2d": [float(i) for i in range(54)]}],
}


def test_valid_pose_loads():
    pose = PoseFile.model_validate(VALID)
    assert pose.canvas_width == 512
    assert len(pose.people) == 1


def test_wrong_body_keypoint_count_rejected():
    bad = {"people": [{"pose_keypoints_2d": [0.0] * 51}]}
    with pytest.raises(ValidationError):
        PoseFile.model_validate(bad)


def test_optional_parts_default_none():
    pose = PoseFile.model_validate(VALID)
    person = pose.people[0]
    assert person.hand_left_keypoints_2d is None
    assert person.face_keypoints_2d is None


def test_keypoints_returns_triplets():
    pose = PoseFile.model_validate(VALID)
    kps = pose.people[0].keypoints("pose_keypoints_2d")
    assert len(kps) == 18
    assert kps[0] == (0.0, 1.0, 2.0)


def test_export_json_schema_has_canvas():
    schema = export_json_schema()
    assert "canvas_width" in schema["properties"]


def test_load_real_sample():
    pose = load_pose(SAMPLE)
    nose = pose.people[0].keypoints("pose_keypoints_2d")[0]
    assert nose == (256.0, 180.0, 0.95)

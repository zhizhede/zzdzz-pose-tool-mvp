"""外部姿态数据导入的单元测试与 API 冒烟。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pose_tool.importers import detect_and_parse
from pose_tool.webapp import create_app


def _openpose_json(**overrides):
    data = {
        "version": "0.2",
        "canvas_width": 512,
        "canvas_height": 512,
        "people": [{"pose_keypoints_2d": [float(i % 54) for i in range(54)]}],
    }
    data.update(overrides)
    return data


def test_detect_openpose_native():
    pose, fmt, warnings = detect_and_parse(_openpose_json())
    assert fmt == "openpose-json"
    assert warnings == []
    assert pose.canvas_width == 512


def test_openpose_without_canvas_gets_default():
    data = _openpose_json()
    del data["canvas_width"], data["canvas_height"], data["version"]
    pose, fmt, warnings = detect_and_parse(data)
    assert fmt == "openpose-json"
    assert pose.canvas_width == 512
    assert any("画布" in w for w in warnings)


def test_openpose_keeps_hands_and_face():
    data = _openpose_json()
    data["people"][0]["hand_left_keypoints_2d"] = [1.0] * 63
    pose, _, _ = detect_and_parse(data)
    assert pose.people[0].hand_left_keypoints_2d == [1.0] * 63


def test_openpose_out_of_range_clamped():
    data = _openpose_json()
    data["people"][0]["pose_keypoints_2d"][0] = 900.0  # nose x 越界
    pose, _, warnings = detect_and_parse(data)
    assert pose.people[0].pose_keypoints_2d[0] == 511.0
    assert any("夹取" in w for w in warnings)


def _coco_json():
    """17 点 COCO：nose(100,100) v2，双肩 v2，其余右半身 v0（缺失）。"""
    kp = [0.0] * 51
    def put(i, x, y, v):
        kp[i * 3], kp[i * 3 + 1], kp[i * 3 + 2] = x, y, v
    put(0, 100, 100, 2)   # nose
    put(5, 80, 140, 2)    # l_sho
    put(6, 120, 140, 2)   # r_sho
    put(8, 130, 180, 2)   # r_elb
    put(13, 90, 240, 2)   # l_kne
    return {"annotations": [{"keypoints": kp, "num_keypoints": 5}]}


def test_coco_mapping_raw():
    """不做画布适配时，17→18 映射必须逐点精确。"""
    from pose_tool.importers import _parse_coco

    pose, warnings = _parse_coco(_coco_json(), fit_to_canvas=False)
    kps = pose.people[0].keypoints("pose_keypoints_2d")
    assert kps[1][:2] == (100.0, 140.0)  # neck = 双肩中点
    assert kps[2][:2] == (120.0, 140.0)  # r_sho <- coco6
    assert kps[5][:2] == (80.0, 140.0)   # l_sho <- coco5
    assert kps[3][:2] == (130.0, 180.0)  # r_elb <- coco8
    assert kps[12][:2] == (90.0, 240.0)  # l_kne <- coco13
    assert kps[4][2] == 0.0              # 缺失点
    assert kps[0][2] == 0.9              # v=2 → 0.9
    assert any("左右" in w for w in warnings)


def test_detect_coco_fits_into_canvas():
    pose, fmt, warnings = detect_and_parse(_coco_json())
    assert fmt == "coco-json"
    for x, y, c in [
        (x, y, c) for x, y, c in pose.people[0].keypoints("pose_keypoints_2d") if c > 0
    ]:
        assert 0 <= x <= 511 and 0 <= y <= 511
    assert any("缩放居中" in w for w in warnings)


def test_coco_neck_falls_back_to_visible_shoulder():
    from pose_tool.importers import _parse_coco

    data = _coco_json()
    kp = data["annotations"][0]["keypoints"]
    kp[15:18] = [0, 0, 0]  # l_sho（coco 下标 5 → kp[15:18]）缺失
    pose, warnings = _parse_coco(data, fit_to_canvas=False)
    kps = pose.people[0].keypoints("pose_keypoints_2d")
    assert kps[1][:2] == (120.0, 140.0)  # 退化为可见的右肩
    assert any("退化" in w for w in warnings)


def test_unknown_structure_raises():
    with pytest.raises(ValueError):
        detect_and_parse({"hello": "world"})


def test_import_api_roundtrip(tmp_path: Path):
    import json

    app = create_app()
    client = TestClient(app)
    r = client.post(
        "/api/import",
        files={"file": ("pose.json", json.dumps(_openpose_json()).encode())},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["format"] == "openpose-json"
    assert len(data["pose"]["people"][0]["pose_keypoints_2d"]) == 54
    assert "angles" in data


def test_import_api_rejects_garbage():
    app = create_app()
    client = TestClient(app)
    r = client.post(
        "/api/import",
        files={"file": ("x.json", b'{"hello": 1}')},
    )
    assert r.status_code == 400


def test_import_api_rejects_non_json():
    app = create_app()
    client = TestClient(app)
    r = client.post("/api/import", files={"file": ("x.json", b"not json")})
    assert r.status_code == 400

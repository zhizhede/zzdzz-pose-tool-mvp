"""recognize / 角度计算的单元测试（不联网）。"""

import math
from pathlib import Path

import pytest

from pose_tool.recognize import _extract_json, load_recognize_config
from pose_tool.schema import PoseFile

ROOT = Path(__file__).resolve().parents[1]


def _recognized_pose() -> PoseFile:
    """模拟一次识别输出：54 个关键点值。"""
    return PoseFile.model_validate({
        "canvas_width": 512,
        "canvas_height": 512,
        "people": [{"pose_keypoints_2d": [float(i % 54) for i in range(54)]}],
    })


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_markdown_fence():
    text = '好的，以下是结果：\n```json\n{"a": 1}\n```\n完毕'
    assert _extract_json(text) == {"a": 1}


def test_extract_json_with_think_block():
    text = '<think>让我分析一下这张图...</think>{"version": "0.2", "canvas_width": 512}'
    assert _extract_json(text) == {"version": "0.2", "canvas_width": 512}


def test_extract_json_no_json_raises():
    with pytest.raises(ValueError):
        _extract_json("图片中看不到人物")


def test_load_config_requires_key(tmp_path: Path):
    cfg = tmp_path / "config.local.yaml"
    cfg.write_text("model: MiniMax-M3\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_recognize_config(cfg)


def test_load_config_defaults(tmp_path: Path):
    cfg = tmp_path / "config.local.yaml"
    cfg.write_text(
        "model: MiniMax-M3\napi_key: sk-test\n", encoding="utf-8"
    )
    config = load_recognize_config(cfg)
    assert config["api_base"] == "https://api.minimaxi.com/v1"
    assert config["timeout_seconds"] == 120


def test_swap_left_right_relabels_not_moves():
    from pose_tool.recognize import swap_left_right

    pose = PoseFile.model_validate({
        "canvas_width": 512,
        "canvas_height": 512,
        "people": [{"pose_keypoints_2d": [
            10, 10, 0.9, 20, 20, 0.9, 30, 30, 0.9, 40, 40, 0.9, 50, 50, 0.9,
            60, 60, 0.9, 70, 70, 0.9, 80, 80, 0.9, 90, 90, 0.9, 100, 100, 0.9,
            110, 110, 0.9, 120, 120, 0.9, 130, 130, 0.9, 140, 140, 0.9,
            150, 150, 0.9, 160, 160, 0.9, 170, 170, 0.9, 180, 180, 0.9,
        ]}],
    })
    swapped = swap_left_right(pose)
    orig = pose.people[0].keypoints("pose_keypoints_2d")
    now = swapped.people[0].keypoints("pose_keypoints_2d")
    # nose(0)/neck(1) 不动
    assert now[0] == orig[0] and now[1] == orig[1]
    # right_shoulder(2) 与 left_shoulder(5) 标签互换
    assert now[2] == orig[5] and now[5] == orig[2]
    # 坐标集合不变（只换标签不移动）
    assert sorted(now) == sorted(orig)
    # 原对象不被修改
    assert pose.people[0].keypoints("pose_keypoints_2d") == orig


def test_recognized_pose_roundtrip(tmp_path: Path):
    """识别结果可被 schema 校验并可落盘再读回。"""
    import json

    pose = _recognized_pose()
    out = tmp_path / "pose.json"
    out.write_text(pose.model_dump_json(), encoding="utf-8")
    loaded = PoseFile.model_validate(json.loads(out.read_text(encoding="utf-8")))
    assert len(loaded.people[0].pose_keypoints_2d) == 54

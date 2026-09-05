"""深度图渲染测试：依赖 DAE 导入产生的 pose_keypoints_3d。"""

from pathlib import Path

import pytest

from pose_tool.collada_import import parse_collada
from pose_tool.depth import render_depth
from pose_tool.render import render_to_png

ROOT = Path(__file__).resolve().parents[1]
SITTING = ROOT / "test-assets" / "Sitting.dae"


@pytest.mark.skipif(not SITTING.exists(), reason="测试素材未下载")
def test_depth_image_structure():
    pose, _, _ = parse_collada(SITTING, frame=0)
    img = render_depth(pose)
    assert img.size == (pose.canvas_width, pose.canvas_height)
    assert img.mode == "L"
    hist = img.histogram()
    background = hist[0]
    body = sum(hist[1:])
    assert body > 1000  # 人体有实体覆盖
    assert background > body  # 背景仍占大头
    assert max(hist[60:]) > 0  # 近处肢体达到明亮灰度


@pytest.mark.skipif(not SITTING.exists(), reason="测试素材未下载")
def test_depth_respects_z_order():
    """近亮远暗： Construct 一个 双关节 伪姿态验证灰度方向。"""
    from pose_tool.schema import PoseFile

    pose = PoseFile.model_validate({
        "version": "0.2",
        "canvas_width": 100,
        "canvas_height": 100,
        "people": [{
            "pose_keypoints_2d": [36.5, 50.0, 0.9, 63.5, 50.0, 0.9] + [0.0] * 48,
            "pose_keypoints_3d": [0.0, 0.0, 1.0, 10.0, 0.0, 10.0] + [0.0] * 48,
        }],
    })
    img = render_depth(pose)
    near = img.getpixel((63, 50))   # z=10 的一端（近）
    far = img.getpixel((37, 50))    # z=1 的一端（远）
    assert near > far  # MiDaS 约定：越近越亮


def test_depth_requires_3d():
    from pose_tool.schema import PoseFile

    pose = PoseFile.model_validate({
        "version": "0.2",
        "canvas_width": 10,
        "canvas_height": 10,
        "people": [{"pose_keypoints_2d": [0.0] * 54}],
    })
    with pytest.raises(ValueError, match="pose_keypoints_3d"):
        render_depth(pose)


def test_schema_3d_field_validation():
    from pydantic import ValidationError

    from pose_tool.schema import PoseFile

    ok = PoseFile.model_validate({
        "canvas_width": 10, "canvas_height": 10,
        "people": [{"pose_keypoints_2d": [0.0] * 54, "pose_keypoints_3d": [0.0] * 54}],
    })
    assert len(ok.people[0].pose_keypoints_3d) == 54
    with pytest.raises(ValidationError):
        PoseFile.model_validate({
            "canvas_width": 10, "canvas_height": 10,
            "people": [{"pose_keypoints_2d": [0.0] * 54, "pose_keypoints_3d": [0.0] * 53}],
        })


def test_skeleton_render_unchanged_by_3d():
    """3D 字段是增量信息：骨架图渲染路径不受影响。"""
    from PIL import Image

    from pose_tool.schema import PoseFile

    pose = PoseFile.model_validate({
        "version": "0.2",
        "canvas_width": 10, "canvas_height": 10,
        "people": [{
            "pose_keypoints_2d": [5.0, 5.0, 0.9] + [0.0] * 51,
            "pose_keypoints_3d": [0.0] * 54,
        }],
    })
    out = render_to_png(pose, Path("_tmp_render_check.png"))
    assert Image.open(out).size == (10, 10)
    out.unlink(missing_ok=True)

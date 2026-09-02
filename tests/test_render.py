import io
from pathlib import Path

from pose_tool.render import render_pose
from pose_tool.schema import load_pose

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "poses" / "looking-down-phone" / "pose.json"


def _png_bytes(pose) -> bytes:
    img = render_pose(pose)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_render_deterministic():
    """同输入必须产出逐字节一致的 PNG（确定性复现是本项目的核心承诺）。"""
    pose = load_pose(SAMPLE)
    assert _png_bytes(pose) == _png_bytes(pose)


def test_render_canvas_size():
    pose = load_pose(SAMPLE)
    assert render_pose(pose).size == (pose.canvas_width, pose.canvas_height)


def test_render_not_empty():
    """黑底骨架图必然有非零字节，全黑说明渲染逻辑坏了。"""
    pose = load_pose(SAMPLE)
    img = render_pose(pose)
    assert img.getextrema()[0][1] > 0 or img.getextrema()[1][1] > 0 or img.getextrema()[2][1] > 0

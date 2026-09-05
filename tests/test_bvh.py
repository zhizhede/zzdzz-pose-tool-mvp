"""BVH 导出测试：核心是 FK 往返校验——导出的旋转必须能还原输入关节位置。"""

import math
from pathlib import Path

import pytest

from pose_tool.bvh import export_bvh
from pose_tool.schema import PoseFile

ROOT = Path(__file__).resolve().parents[1]
SITTING = ROOT / "test-assets" / "Sitting.dae"


def _parse_bvh(text: str):
    """极简 BVH 解析：返回 (层级 dict, MOTION 首帧数值)。"""
    lines = [l.split("//")[0].strip() for l in text.splitlines()]
    joints: dict[str, dict] = {}
    stack: list[str] = []
    for l in lines:
        if l.startswith(("ROOT ", "JOINT ")):
            name = l.split()[1]
            parent = stack[-1] if stack else None
            joints[name] = {"parent": parent, "offset": None, "channels": None, "children": []}
            if parent:
                joints[parent].setdefault("children", []).append(name)
            stack.append(name)
        elif l.startswith("End Site"):
            name = f"{stack[-1]}_end"
            joints[name] = {"parent": stack[-1], "offset": None, "channels": None,
                            "children": [], "end": True}
            stack.append(name)
        elif l.startswith("OFFSET"):
            joints[stack[-1]]["offset"] = [float(v) for v in l.split()[1:4]]
        elif l.startswith("CHANNELS"):
            joints[stack[-1]]["channels"] = int(l.split()[1])
        elif l.startswith("}"):
            stack.pop()

    frame = []
    for l in text.split("MOTION")[1].splitlines():
        l = l.strip()
        if l and not l.startswith(("Frames", "Frame Time")):
            frame = [float(v) for v in l.split()]
            break
    return joints, frame


def _fk(joints: dict, frame: list[float]):
    """前向运动学：返回 关节名 → 世界坐标（欧拉合成序 R=Rz·Rx·Ry）。"""
    def euler_mat(vals):
        z, x, y = [math.radians(v) for v in vals]
        cz, sz = math.cos(z), math.sin(z)
        cx, sx = math.cos(x), math.sin(x)
        cy, sy = math.cos(y), math.sin(y)
        return [[cz * cy - sz * sx * sy, -sz * cx, cz * sy + sz * sx * cy],
                [sz * cy + cz * sx * sy, cz * cx, sz * sy - cz * sx * cy],
                [-cx * sy, sx, cx * cy]]

    world: dict[str, tuple] = {}
    cursor = [0]  # MOTION 帧值的顺序消费游标（与层级遍历同序）

    def walk(name, parent_pos, parent_rot):
        j = joints[name]
        off = j["offset"]
        if j["channels"]:
            n = j["channels"]
            if name == "Hips":
                pos = (frame[0], frame[1], frame[2])
                angles = frame[3:6]
            else:
                pos = parent_pos
                angles = frame[cursor[0]:cursor[0] + 3]
            cursor[0] += n
            R_local = euler_mat(angles)
        else:
            pos = parent_pos
            R_local = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        R_world = [[sum(parent_rot[i][k] * R_local[k][j] for k in range(3))
                    for j in range(3)] for i in range(3)]
        world[name] = (
            pos[0] + sum(R_world[0][k] * off[k] for k in range(3)),
            pos[1] + sum(R_world[1][k] * off[k] for k in range(3)),
            pos[2] + sum(R_world[2][k] * off[k] for k in range(3)),
        )
        for child in j["children"]:
            walk(child, world[name], R_world)

    walk("Hips", (0.0, 0.0, 0.0), [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    return world


@pytest.mark.skipif(not SITTING.exists(), reason="测试素材未下载")
def test_bvh_roundtrip_reconstructs_positions():
    """核心校验：BVH 里的旋转经 FK 后必须还原输入的关节 3D 位置。"""
    from pose_tool.collada_import import parse_collada

    pose, _, _ = parse_collada(SITTING, frame=0)
    text = export_bvh(pose)
    joints, frame = _parse_bvh(text)
    assert "Frames: 1" in text
    assert "RightArm" in joints and "LeftFoot" in joints

    world = _fk(joints, frame)
    p = pose.people[0]
    raw = p.pose_keypoints_3d
    p3 = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]

    expected = {
        "Neck": p3[1],
        "RightShoulder": p3[2], "RightArm": p3[3], "RightHand": p3[4],
        "LeftShoulder": p3[5], "LeftArm": p3[6], "LeftHand": p3[7],
        "RightUpLeg": p3[8], "RightLeg": p3[9], "RightFoot": p3[10],
        "LeftUpLeg": p3[11], "LeftLeg": p3[12], "LeftFoot": p3[13],
    }
    worst_name, worst_err = "", 0.0
    for name, want in expected.items():
        err = math.dist(world[name], want)
        if err > worst_err:
            worst_name, worst_err = name, err
    assert worst_err < 0.05, f"{worst_name} 往返误差 {worst_err:.4f}"


def test_bvh_requires_3d():
    pose = PoseFile.model_validate({
        "version": "0.2", "canvas_width": 10, "canvas_height": 10,
        "people": [{"pose_keypoints_2d": [0.0] * 54}],
    })
    with pytest.raises(ValueError, match="pose_keypoints_3d"):
        export_bvh(pose)


def test_bvh_structure_contains_skeleton():
    from pose_tool.collada_import import parse_collada
    import os
    if not SITTING.exists():
        pytest.skip("测试素材未下载")
    pose, _, _ = parse_collada(SITTING, frame=0)
    text = export_bvh(pose)
    for token in ("HIERARCHY", "ROOT Hips", "MOTION", "Frames: 1", "JOINT RightArm"):
        assert token in text

"""Collada 导入测试：合成最小 DAE 夹具 + 真实 Mixamo 文件冒烟（存在才跑）。"""

import json
from pathlib import Path

import pytest

from pose_tool.collada_import import parse_collada

ROOT = Path(__file__).resolve().parents[1]
CAPOEIRA = ROOT / "test-assets" / "Capoeira.dae"
SITTING = ROOT / "test-assets" / "Sitting.dae"

MINIMAL_DAE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit name="centimeter" meter="0.01"/><up_axis>Y_UP</up_axis></asset>
  <library_visual_scenes>
    <visual_scene id="Scene">
      <node id="Hips" name="mixamorig_Hips" type="JOINT">
        <matrix sid="transform">1 0 0 0  0 1 0 100  0 0 1 0  0 0 0 1</matrix>
        <node id="LeftUpLeg" name="mixamorig_LeftUpLeg" type="JOINT">
          <matrix sid="transform">1 0 0 0  0 1 0 -10  0 0 1 0  0 0 0 1</matrix>
          <node id="LeftLeg" name="mixamorig_LeftLeg" type="JOINT">
            <matrix sid="transform">1 0 0 0  0 1 0 -5  0 0 1 0  0 0 0 1</matrix>
          </node>
        </node>
      </node>
    </visual_scene>
  </library_visual_scenes>
  <library_animations>
    <animation id="LeftLeg_anim">
      <source id="times"><float_array id="times-arr" count="2">0 1</float_array></source>
      <source id="output"><float_array id="output-arr" count="32">
        1 0 0 0  0 1 0 -40  0 0 1 0  0 0 0 1
        1 0 0 0  0 1 0 -45  0 0 1 0  0 0 0 1
      </float_array></source>
      <sampler id="s">
        <input semantic="INPUT" source="#times"/>
        <input semantic="OUTPUT" source="#output"/>
      </sampler>
      <channel target="mixamorig_LeftLeg/matrix" source="#s"/>
    </animation>
  </library_animations>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""


# 朝向判定夹具：Hips 携带绕 Y 轴三帧旋转（0°/90°/180°）+ Head 骨骼映射 slot 0
FACE_DAE = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit name="centimeter" meter="0.01"/><up_axis>Y_UP</up_axis></asset>
  <library_visual_scenes>
    <visual_scene id="Scene">
      <node id="Hips" name="mixamorig_Hips" type="JOINT">
        <matrix sid="transform">1 0 0 0  0 1 0 100  0 0 1 0  0 0 0 1</matrix>
        <node id="Neck" name="mixamorig_Neck" type="JOINT">
          <matrix sid="transform">1 0 0 0  0 1 0 12  0 0 1 0  0 0 0 1</matrix>
          <node id="Head" name="mixamorig_Head" type="JOINT">
            <matrix sid="transform">1 0 0 0  0 1 0 10  0 0 1 0  0 0 0 1</matrix>
          </node>
        </node>
      </node>
    </visual_scene>
  </library_visual_scenes>
  <library_animations>
    <animation id="Hips_anim">
      <source id="times"><float_array id="times-arr" count="3">0 1 2</float_array></source>
      <source id="output"><float_array id="output-arr" count="48">
        1 0 0 0  0 1 0 0  0 0 1 0  0 0 0 1
        0 0 1 0  0 1 0 0  -1 0 0 0  0 0 0 1
        -1 0 0 0  0 1 0 0  0 0 -1 0  0 0 0 1
      </float_array></source>
      <sampler id="s">
        <input semantic="INPUT" source="#times"/>
        <input semantic="OUTPUT" source="#output"/>
      </sampler>
      <channel target="mixamorig_Hips/matrix" source="#s"/>
    </animation>
  </library_animations>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""


def test_facing_front_profile_back():
    p0, w0, _ = parse_collada(FACE_DAE, frame=0)
    assert p0.people[0].facing == "front"
    assert p0.people[0].keypoints("pose_keypoints_2d")[0][2] > 0  # 鼻子可见

    p1, w1, _ = parse_collada(FACE_DAE, frame=1)
    assert p1.people[0].facing == "profile"
    assert p1.people[0].keypoints("pose_keypoints_2d")[0][2] > 0

    p2, w2, _ = parse_collada(FACE_DAE, frame=2)
    assert p2.people[0].facing == "back"
    kps2 = p2.people[0].keypoints("pose_keypoints_2d")
    # 背面：五官点全部隐藏（鼻 + 双眼 + 双耳）
    assert all(kps2[i][2] == 0.0 for i in (0, 14, 15, 16, 17))
    assert any("back" in w for w in w2)


def test_facing_no_rotation_defaults_front():
    # MINIMAL_DAE 无 Head/Neck 骨骼，回退 Hips；仅平移不改朝向 → 仍判 front
    pose, _, _ = parse_collada(MINIMAL_DAE, frame=0)
    assert pose.people[0].facing == "front"


def test_schema_facing_validation():
    from pydantic import ValidationError

    from pose_tool.schema import PoseFile

    base = {"canvas_width": 10, "canvas_height": 10,
            "people": [{"pose_keypoints_2d": [0.0] * 54, "facing": "back"}]}
    assert PoseFile.model_validate(base).people[0].facing == "back"
    ok_none = PoseFile.model_validate({**base, "people": [{"pose_keypoints_2d": [0.0] * 54}]})
    assert ok_none.people[0].facing is None
    bad = {**base, "people": [{"pose_keypoints_2d": [0.0] * 54, "facing": "left"}]}
    with pytest.raises(ValidationError):
        PoseFile.model_validate(bad)


def test_minimal_dae_fk_and_frame_selection():
    pose, warnings, total = parse_collada(MINIMAL_DAE, frame=0)
    assert total == 2
    kps = pose.people[0].keypoints("pose_keypoints_2d")
    # 夹具只有 3 根骨骼：Hips（骨盆根，不映射 18 点）、LeftUpLeg(11)、LeftLeg(12)
    assert kps[11][2] > 0 and kps[12][2] > 0
    assert kps[1][2] == 0.0  # 无 Neck 骨骼
    # 结构关系：髋在膝上方（投影后 y 更小）
    assert kps[11][1] < kps[12][1]


def test_minimal_dae_frame1_differs():
    p0, _, _ = parse_collada(MINIMAL_DAE, frame=0)
    p1, _, _ = parse_collada(MINIMAL_DAE, frame=1)
    k0 = p0.people[0].pose_keypoints_2d
    k1 = p1.people[0].pose_keypoints_2d
    assert k0 != k1  # 两帧的 LeftLeg 局部平移不同


def test_frame_out_of_range():
    with pytest.raises(ValueError, match="越界"):
        parse_collada(MINIMAL_DAE, frame=99)


@pytest.mark.skipif(not CAPOEIRA.exists(), reason="测试素材未下载")
def test_capoeira_smoke():
    pose, warnings, total = parse_collada(CAPOEIRA, frame=0)
    assert total == 103
    kps = pose.people[0].keypoints("pose_keypoints_2d")
    visible = [k for k in kps if k[2] > 0]
    assert len(visible) == 14  # 身体 14 点全映射，眼耳 4 点无骨骼留隐藏
    for x, y, c in visible:
        assert 0 <= x <= 511 and 0 <= y <= 511
    assert any("103" in w for w in warnings)


@pytest.mark.skipif(not (CAPOEIRA.exists() and SITTING.exists()), reason="测试素材未下载")
def test_two_files_differ():
    p_cap, _, _ = parse_collada(CAPOEIRA, frame=0)
    p_sit, _, _ = parse_collada(SITTING, frame=0)
    assert p_cap.people[0].pose_keypoints_2d != p_sit.people[0].pose_keypoints_2d


@pytest.mark.skipif(not CAPOEIRA.exists(), reason="测试素材未下载")
def test_api_import_dae():
    from fastapi.testclient import TestClient

    from pose_tool.webapp import create_app

    client = TestClient(create_app())
    r = client.post(
        "/api/import?frame=10",
        files={"file": ("Capoeira.dae", CAPOEIRA.read_bytes())},
        data={"frame": "10"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["format"] == "collada"
    assert data["total_frames"] == 103
    assert len(data["pose"]["people"][0]["pose_keypoints_2d"]) == 54

"""DWPose 识别模块测试：模型/图片就绪才跑真推理，其余验证映射表。"""

from pathlib import Path

import pytest

from pose_tool.dwpose import C17_TO_18, DEFAULT_MODEL_DIR

ROOT = Path(__file__).resolve().parents[1]
MODELS_OK = (DEFAULT_MODEL_DIR / "yolox_l.onnx").exists() is False  # yolox 官方损坏，走整图回退
POSE_MODEL_OK = (DEFAULT_MODEL_DIR / "dw-ll_ucoco_384.onnx").exists()
TEST_IMAGE = Path(r"C:/Users/ZZDZZ/Downloads/identity_pose_test_00008_.png")


def test_c17_to_18_mapping_covers_18_points():
    """映射表必须产出 18 个目标点，且身体左右不串（COCO 6=人物左肩）。"""
    assert len(C17_TO_18) == 18
    assert C17_TO_18[0] == 0            # 鼻
    assert C17_TO_18[1] is None         # 颈合成
    body_pairs = [(2, 5), (3, 6), (4, 7), (8, 11), (9, 12), (10, 13)]
    for r, l in body_pairs:
        assert C17_TO_18[r] > C17_TO_18[l]  # COCO 右侧下标恒大于左侧
    assert sorted(v for v in C17_TO_18 if v is not None) == list(range(17))


def test_missing_pose_model_raises():
    from pose_tool.dwpose import DWPoseDetector

    if POSE_MODEL_OK:
        pytest.skip("模型已安装，跳过缺失场景")
    with pytest.raises(FileNotFoundError):
        DWPoseDetector()


@pytest.mark.skipif(not (POSE_MODEL_OK and TEST_IMAGE.exists()),
                    reason="DWPose 模型或测试图片未就绪")
def test_detect_returns_valid_18_points():
    from pose_tool.dwpose import DWPoseDetector

    det = DWPoseDetector()
    kps = det(TEST_IMAGE)
    assert kps.shape == (18, 3)
    assert (kps[:, 2] > 0.1).sum() >= 12      # 大部分点有置信度
    ys = kps[:, 1]
    assert ys.min() < ys.max()                # 有空间分布
    # 髋在膝上方（站立图）
    assert kps[8][1] < kps[9][1] and kps[11][1] < kps[12][1]


def test_detect_to_pose_dict_schema():
    from pose_tool.dwpose import detect_to_pose_dict

    if not (POSE_MODEL_OK and TEST_IMAGE.exists()):
        pytest.skip("DWPose 模型或测试图片未就绪")
    data = detect_to_pose_dict(TEST_IMAGE)
    assert data["version"] == "0.2"
    assert data["meta"]["source_format"] == "dwpose-image"
    person = data["people"][0]
    assert len(person["pose_keypoints_2d"]) == 54
    assert "pose_keypoints_3d" not in person  # 2D 资产不含 3D

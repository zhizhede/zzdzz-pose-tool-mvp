"""pose.json 数据格式定义。

关键点布局与 openpose-editor / ControlNet-OpenPose 生态保持一致：
body 固定 18 点（OpenPose COCO-18 顺序），手部 21 点 × 2、面部 70 点可选。
所有关键点均为 [x, y, conf] 扁平三元组数组，conf <= 0 表示缺失。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

N_BODY_KEYPOINTS = 18

# OpenPose COCO-18 顺序（与 controlnet_aux 渲染的下标一致）
BODY_KEYPOINT_NAMES = [
    "nose", "neck", "right_shoulder", "right_elbow", "right_wrist",
    "left_shoulder", "left_elbow", "left_wrist", "right_hip", "right_knee",
    "right_ankle", "left_hip", "left_knee", "left_ankle", "right_eye",
    "left_eye", "right_ear", "left_ear",
]

KEYPOINT_PART_COUNTS = {
    "pose_keypoints_2d": N_BODY_KEYPOINTS,
    "hand_left_keypoints_2d": 21,
    "hand_right_keypoints_2d": 21,
    "face_keypoints_2d": 70,
}


FACE_FACING_VALUES = ("front", "back", "profile")


class Person(BaseModel):
    """单个人物的关键点集合。"""

    model_config = ConfigDict(extra="ignore")

    pose_keypoints_2d: list[float]
    hand_left_keypoints_2d: Optional[list[float]] = None
    hand_right_keypoints_2d: Optional[list[float]] = None
    face_keypoints_2d: Optional[list[float]] = None
    # 人物朝向（3D 导入时判定）：front=面向观察者 / back=背对 / profile=侧面。
    # 可选字段，旧文件缺省即兼容；back 的骨架图不画五官点（见渲染约定）。
    facing: Optional[str] = None
    # 3D 关节坐标（18 点 × [x,y,z]，导入时的世界系真值，单位与 rig 一致）。
    # 可选字段：深度图渲染（preview_depth.png）的唯一依据，编辑器拖 2D 点不更新它。
    pose_keypoints_3d: Optional[list[float]] = None

    @field_validator("facing")
    @classmethod
    def _check_facing(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in FACE_FACING_VALUES:
            raise ValueError(f"facing 只能是 {'/'.join(FACE_FACING_VALUES)} 或缺省，实际 {v!r}")
        return v

    @field_validator("pose_keypoints_3d")
    @classmethod
    def _check_3d(cls, v: Optional[list[float]]) -> Optional[list[float]]:
        if v is not None and len(v) != N_BODY_KEYPOINTS * 3:
            raise ValueError(f"pose_keypoints_3d 需要 {N_BODY_KEYPOINTS * 3} 个数（18 点 × [x,y,z]），实际 {len(v)} 个")
        return v

    @field_validator(*KEYPOINT_PART_COUNTS, check_fields=False)
    @classmethod
    def _check_flat_triplets(cls, v: Optional[list[float]], info):
        if v is None:
            return v
        points = KEYPOINT_PART_COUNTS[info.field_name]
        expected = points * 3
        if len(v) != expected:
            raise ValueError(
                f"{info.field_name} 需要 {expected} 个数（{points} 点 × [x,y,conf]），实际 {len(v)} 个"
            )
        return v

    def keypoints(self, part: str) -> list[tuple[float, float, float]]:
        """把指定部位的扁平数组切成 (x, y, conf) 三元组列表。"""
        data = getattr(self, part)
        return [(data[i], data[i + 1], data[i + 2]) for i in range(0, len(data), 3)]


class PoseFile(BaseModel):
    """pose.json 顶层结构。字段名与 openpose-editor 的 JSON 相互兼容。"""

    model_config = ConfigDict(extra="ignore")

    version: str = "0.2"
    canvas_width: int = Field(default=512, gt=0)
    canvas_height: int = Field(default=512, gt=0)
    people: list[Person] = Field(min_length=1)
    meta: dict[str, Any] = Field(default_factory=dict)


def load_pose(path: str | Path) -> PoseFile:
    return PoseFile.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def export_json_schema() -> dict[str, Any]:
    """pydantic 模型是唯一事实来源，schema 文件由它导出。"""
    return PoseFile.model_json_schema()

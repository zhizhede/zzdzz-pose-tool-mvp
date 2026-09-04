"""外部姿态数据导入：openpose-editor JSON / COCO 标注 → pose.json 格式。

导入只做格式转换与归一化，不落盘——载入编辑器人工确认后由另存为入库，
与"识别是草稿"同一哲学。返回的 warnings 供前端展示给用户。
"""

from __future__ import annotations

import math
from typing import Any

from .schema import PoseFile

CANVAS_DEFAULT = 512

# OpenPose-18 下标 -> COCO-17 下标（neck=op[1] 特殊：双肩中点，不在表内）
_OP_FROM_COCO = {
    0: 0,                    # nose
    2: 6, 3: 8, 4: 10,       # right_shoulder / elbow / wrist
    5: 5, 6: 7, 7: 9,        # left_shoulder / elbow / wrist
    8: 12, 9: 14, 10: 16,    # right_hip / knee / ankle
    11: 11, 12: 13, 13: 15,  # left_hip / knee / ankle
    14: 2, 15: 1,            # right_eye / left_eye
    16: 4, 17: 3,            # right_ear / left_ear
}

# COCO 可见性标记 -> 置信度
_COCO_VIS_TO_CONF = {0: 0.0, 1: 0.6, 2: 0.9}


def _clamp_into_canvas(pose: PoseFile, warnings: list[str]) -> None:
    for p_idx, person in enumerate(pose.people):
        flat = person.pose_keypoints_2d
        for i in range(0, len(flat), 3):
            if flat[i + 2] <= 0:
                continue
            x, y = flat[i], flat[i + 1]
            nx = min(max(x, 0.0), pose.canvas_width - 1.0)
            ny = min(max(y, 0.0), pose.canvas_height - 1.0)
            if (nx, ny) != (x, y):
                warnings.append(
                    f"第 {p_idx} 人关键点 {i // 3} 越出画布，已夹取到画布内"
                )
                flat[i], flat[i + 1] = nx, ny


def _parse_openpose(data: dict[str, Any]) -> tuple[PoseFile, list[str]]:
    warnings: list[str] = []
    payload = dict(data)
    if "canvas_width" not in payload or "canvas_height" not in payload:
        warnings.append("缺少画布尺寸，按 512×512 处理")
    payload.setdefault("canvas_width", CANVAS_DEFAULT)
    payload.setdefault("canvas_height", CANVAS_DEFAULT)

    pose = PoseFile.model_validate(payload)
    if "version" not in payload:
        warnings.append("缺少 version 字段，按 0.2 处理")
        pose.version = "0.2"
    if not pose.meta and data.get("description"):
        pose.meta = {"description": data["description"]}
    _clamp_into_canvas(pose, warnings)
    return pose, warnings


def _coco_keypoint(kp: list[Any], index: int) -> tuple[float, float, float]:
    x, y, v = kp[index * 3], kp[index * 3 + 1], kp[index * 3 + 2]
    conf = _COCO_VIS_TO_CONF.get(int(v), 0.0)
    return float(x), float(y), conf


def _parse_coco(data: dict[str, Any], fit_to_canvas: bool = True) -> tuple[PoseFile, list[str]]:
    warnings: list[str] = []
    kp = None
    if isinstance(data.get("annotations"), list):
        for ann in data["annotations"]:
            if ann.get("keypoints"):
                kp = ann["keypoints"]
                break
    elif isinstance(data.get("keypoints"), list):
        kp = data["keypoints"]
    if not kp or len(kp) < 51:
        raise ValueError("COCO 标注中未找到 17 点 keypoints 数组")

    pts = [_coco_keypoint(kp, i) for i in range(17)]

    # neck：双肩中点；某肩不可见时退化为可见肩；都不可见则置缺失
    l_sho, r_sho = pts[5], pts[6]
    if l_sho[2] > 0 and r_sho[2] > 0:
        neck = ((l_sho[0] + r_sho[0]) / 2, (l_sho[1] + r_sho[1]) / 2, min(l_sho[2], r_sho[2]))
    elif l_sho[2] > 0:
        neck = l_sho
        warnings.append("右肩不可见，neck 已退化为左肩位置")
    elif r_sho[2] > 0:
        neck = r_sho
        warnings.append("左肩不可见，neck 已退化为右肩位置")
    else:
        neck = (0.0, 0.0, 0.0)

    slots: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * 18
    slots[1] = neck
    for op_idx, coco_idx in _OP_FROM_COCO.items():
        slots[op_idx] = pts[coco_idx]

    flat: list[float] = []
    for x, y, c in slots:
        flat.extend([x, y, c])

    pose = PoseFile.model_validate({
        "version": "0.2",
        "canvas_width": CANVAS_DEFAULT,
        "canvas_height": CANVAS_DEFAULT,
        "people": [{"pose_keypoints_2d": flat}],
    })

    # COCO 坐标处于原图像素系且无画布信息：按可见点包围盒缩放居中到画布
    visible = [(x, y) for x, y, c in flat_iter(pose) if c > 0]
    if visible:
        xs, ys = [p[0] for p in visible], [p[1] for p in visible]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if w > 0 and h > 0:
            scale = min(CANVAS_DEFAULT * 0.9 / w, CANVAS_DEFAULT * 0.9 / h, 10.0)
        else:
            scale = 1.0
        cx = (max(xs) + min(xs)) / 2
        cy = (max(ys) + min(ys)) / 2
        if fit_to_canvas:
            for person in pose.people:
                f = person.pose_keypoints_2d
                for i in range(0, len(f), 3):
                    if f[i + 2] <= 0:
                        continue
                    f[i] = round((f[i] - cx) * scale + CANVAS_DEFAULT / 2, 1)
                    f[i + 1] = round((f[i + 1] - cy) * scale + CANVAS_DEFAULT / 2, 1)
            warnings.append("COCO 无画布信息，已按包围盒缩放居中到 512 画布")
    warnings.append("COCO 左右为解剖学约定，导入后请目视核对方向")

    _clamp_into_canvas(pose, warnings)
    return pose, warnings


def flat_iter(pose: PoseFile):
    for person in pose.people:
        f = person.pose_keypoints_2d
        for i in range(0, len(f), 3):
            yield f[i], f[i + 1], f[i + 2]


def detect_and_parse(data: Any) -> tuple[PoseFile, str, list[str]]:
    """自动探测格式并解析，返回 (pose, 格式名, warnings)。"""
    if not isinstance(data, dict):
        raise ValueError("顶层必须是 JSON 对象")
    people = data.get("people")
    if isinstance(people, list) and any(
        isinstance(p, dict) and "pose_keypoints_2d" in p for p in people
    ):
        pose, warnings = _parse_openpose(data)
        return pose, "openpose-json", warnings
    if "annotations" in data or "keypoints" in data:
        pose, warnings = _parse_coco(data)
        return pose, "coco-json", warnings
    raise ValueError(
        "无法识别的 JSON 结构：需要 openpose-editor 格式（含 people[].pose_keypoints_2d）"
        "或 COCO 标注格式（含 annotations[].keypoints）"
    )

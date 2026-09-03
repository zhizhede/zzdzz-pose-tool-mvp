"""AI 识图工作流：输入图片 → 视觉模型提取姿态关键点 → 导出 pose.json。

连接信息（API 密钥等）从 config.local.yaml 读取，该文件被 .gitignore 排除，
永不提交到 git。参考 config.example.yaml 创建本地配置。
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import yaml

from .schema import PoseFile

DEFAULT_CONFIG_PATH = "config.local.yaml"

# 18 关键点顺序即 schema.BODY_KEYPOINT_NAMES，提示词里逐个中英对照，降低模型错位概率
_PROMPT_TEMPLATE = """你是人体姿态分析引擎。分析图片中人物的姿态，输出 OpenPose COCO-18 关键点坐标。

18 个关键点的顺序固定为（下标从 0 开始）：
0 nose(鼻), 1 neck(颈,约两肩中点), 2 right_shoulder(右肩), 3 right_elbow(右肘), 4 right_wrist(右手腕), 5 left_shoulder(左肩), 6 left_elbow(左肘), 7 left_wrist(左手腕), 8 right_hip(右髋), 9 right_knee(右膝), 10 right_ankle(右踝), 11 left_hip(左髋), 12 left_knee(左膝), 13 left_ankle(左踝), 14 right_eye(右眼), 15 left_eye(左眼), 16 right_ear(右耳), 17 left_ear(左耳)。
左右约定（必须严格遵守，本项目的存储约定）：按观察者视角判断——画面左侧的肩/臂/髋/腿一律用 left_*，画面右侧一律用 right_*。禁止按人物解剖学左右翻转，即使人物面向镜头。

把图片视为 {w}x{h} 的画布，输出每个关键点的像素坐标。
要求：
- c 为 0~1 的可见度置信度；被遮挡或不可见的关键点坐标写 0,0 且 c=0
- 严格按照以下 JSON 结构输出，不要输出任何其他文字、解释或 markdown 代码块

{{"version":"0.2","canvas_width":{w},"canvas_height":{h},"people":[{{"pose_keypoints_2d":[x0,y0,c0,x1,y1,c1,...共54个数...]}}]}}"""


def load_recognize_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"未找到识别配置 {path}。请复制 config.example.yaml 为 config.local.yaml 并填入 API 密钥"
            "（config.local.yaml 已被 .gitignore 排除，不会被提交）"
        )
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for field in ("api_key", "model"):
        if not config.get(field):
            raise ValueError(f"识别配置缺少必填字段: {field}")
    config.setdefault("api_base", "https://api.minimaxi.com/v1")
    config.setdefault("timeout_seconds", 120)
    return config


def _extract_json(text: str) -> dict[str, Any]:
    """从模型回复中提取 JSON。兼容 <think> 推理块和 markdown 代码围栏。"""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```(?:json)?|```", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"模型回复中未找到 JSON：{text[:200]!r}...")
    return json.loads(cleaned[start:end + 1])


def _chat(config: dict[str, Any], messages: list[dict[str, Any]]) -> str:
    import requests

    url = config["api_base"].rstrip("/") + "/chat/completions"
    resp = requests.post(
        url,
        json={
            "model": config["model"],
            "messages": messages,
            "temperature": 0,
        },
        headers={"Authorization": f"Bearer {config['api_key']}"},
        timeout=config["timeout_seconds"],
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# 左右互换的 COCO-18 关键点对；nose(0)/neck(1) 无左右属性不换
_SWAP_PAIRS = [(2, 5), (3, 6), (4, 7), (8, 11), (9, 12), (10, 13), (14, 15), (16, 17)]


def swap_left_right(pose: PoseFile) -> PoseFile:
    """互换左右关键点标签（不动坐标）。

    MLLM 对无解剖学线索的图（骨架/剪影）会系统性颠倒左右，
    识别结果目视确认左右反了之后，用此函数一次性修正。
    """
    pose = pose.model_copy(deep=True)
    for person in pose.people:
        flat = person.pose_keypoints_2d
        for a, b in _SWAP_PAIRS:
            ia, ib = a * 3, b * 3
            flat[ia:ia + 3], flat[ib:ib + 3] = flat[ib:ib + 3], flat[ia:ia + 3]
        if person.hand_left_keypoints_2d and person.hand_right_keypoints_2d:
            person.hand_left_keypoints_2d, person.hand_right_keypoints_2d = (
                person.hand_right_keypoints_2d, person.hand_left_keypoints_2d,
            )
    return pose


def recognize_image(
    image_path: str | Path,
    config: dict[str, Any],
    canvas_width: int = 512,
    canvas_height: int = 512,
    swap_sides: bool = False,
) -> PoseFile:
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

    messages = [{
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text",
             "text": _PROMPT_TEMPLATE.format(w=canvas_width, h=canvas_height)},
        ],
    }]
    data = _extract_json(_chat(config, messages))

    pose = PoseFile.model_validate(data)
    pose.version = "0.2"
    pose.canvas_width = canvas_width
    pose.canvas_height = canvas_height
    if swap_sides:
        pose = swap_left_right(pose)

    # 兜底：模型可能输出 0~1 归一化坐标；统一换算并夹取到画布内
    for person in pose.people:
        flat = person.pose_keypoints_2d
        visible = [flat[i] for i in range(0, len(flat), 3) if flat[i + 2] > 0]
        if visible and max(visible) <= 1.5 and all(v >= -0.5 for v in visible):
            flat = [
                v * canvas_width if i % 3 == 0
                else v * canvas_height if i % 3 == 1
                else v
                for i, v in enumerate(flat)
            ]
        for i in range(0, len(flat), 3):
            if flat[i + 2] > 0:
                flat[i] = min(max(flat[i], 0.0), canvas_width - 1.0)
                flat[i + 1] = min(max(flat[i + 1], 0.0), canvas_height - 1.0)
        person.pose_keypoints_2d = flat
    return pose

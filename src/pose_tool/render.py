"""把 pose.json 渲染成 ControlNet-OpenPose 风格骨架图。

颜色表与肢体连接和 controlnet_aux.util.draw_bodypose 完全一致——
ControlNet-OpenPose 是在这套视觉分布上训练的，随手换颜色/线宽会降低模型响应。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .schema import PoseFile

# 肢体连接使用 1 起始下标，指向 18 个身体关键点
LIMB_SEQ = [
    [2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10],
    [10, 11], [2, 12], [12, 13], [13, 14], [2, 16], [16, 17], [17, 18],
    [2, 15], [15, 14],
]

LIMB_COLORS = [
    (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0),
    (85, 255, 0), (0, 255, 0), (0, 255, 85), (0, 255, 170), (0, 255, 255),
    (0, 170, 255), (0, 85, 255), (0, 0, 255), (85, 0, 255), (170, 0, 255),
    (255, 0, 255), (255, 0, 170), (255, 0, 85),
]

STICK_WIDTH = 4
KEYPOINT_RADIUS = 4
# 对应参考实现里 cv2.GaussianBlur(7x7) 的等效 sigma
BLUR_RADIUS = 1.4


def render_pose(pose: PoseFile, person_index: int = 0) -> Image.Image:
    person = pose.people[person_index]
    pts = person.keypoints("pose_keypoints_2d")

    def kp(i: int) -> tuple[float, float, float]:
        return pts[i - 1]

    canvas = Image.new("RGBA", (pose.canvas_width, pose.canvas_height), (0, 0, 0, 255))

    for i, (a, b) in enumerate(LIMB_SEQ):
        xa, ya, ca = kp(a)
        xb, yb, cb = kp(b)
        if ca <= 0 or cb <= 0:
            continue
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.line([xa, ya, xb, yb], fill=LIMB_COLORS[i] + (255,), width=STICK_WIDTH)
        layer = layer.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
        canvas = Image.alpha_composite(canvas, layer)

    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for j, (x, y, c) in enumerate(pts):
        if c <= 0:
            continue
        r = KEYPOINT_RADIUS
        draw.ellipse([x - r, y - r, x + r, y + r], fill=LIMB_COLORS[j] + (255,))
    canvas = Image.alpha_composite(canvas, layer)

    return canvas.convert("RGB")


def render_to_png(pose: PoseFile, output: str | Path, person_index: int = 0) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    render_pose(pose, person_index=person_index).save(output, format="PNG")
    return output

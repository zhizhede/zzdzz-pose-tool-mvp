"""从 pose.json 的 3D 关节真值渲染深度控制图（ControlNet-Depth 输入）。

相机与 render.py 的 2D 投影完全一致（正交、同一画布/比例/地面锚定），
因此骨架图与深度图逐像素对位。渲染用胶囊体近似肢体、球体近似头部，
画家算法按远→近排序绘制（近处覆盖远处），灰度即深度：
MiDaS 约定 **越近越亮**，背景纯黑。
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .render import LIMB_SEQ
from .schema import PoseFile

SCALE = 2  # 超采样倍数（抗锯齿）
BLUR_RADIUS = 2.0

# 肢体半径系数（× 头颈距 d）
RADIUS_HEAD = 0.62
RADIUS_TORSO = 0.45
RADIUS_LIMB = 0.30

_ARM = {2, 3, 4, 5, 6, 7}   # 0 起下标：双肩/肘/腕
_LEG = {8, 9, 10, 11, 12, 13}


def _limb_radius(ja: int, jb: int, d: float) -> float:
    """按关节对（0 起下标）估肢体半径。"""
    pair = {ja, jb}
    if pair <= _ARM:
        return RADIUS_LIMB * d
    if pair <= _LEG:
        return 0.38 * d
    if pair <= {1, 2, 5, 8, 11}:
        return RADIUS_TORSO * d
    return RADIUS_LIMB * d  # 颈→面部/耳的连接线（在头球内，仅衔接用）


def render_depth(pose: PoseFile, person_index: int = 0) -> Image.Image:
    person = pose.people[person_index]
    if not person.pose_keypoints_3d:
        raise ValueError(
            "该姿态没有 pose_keypoints_3d（仅 DAE 导入的资产携带 3D 真值），无法渲染深度图"
        )
    pts3d = [
        tuple(person.pose_keypoints_3d[i:i + 3])
        for i in range(0, len(person.pose_keypoints_3d), 3)
    ]
    kps2d = person.keypoints("pose_keypoints_2d")
    alive = [i for i in range(18) if kps2d[i][2] > 0 and any(v != 0.0 for v in pts3d[i])]
    if len(alive) < 2:
        raise ValueError("2D/3D 关节数据不足，无法渲染深度图")

    # 比例单位：头颈距（与导入端的面部合成同基准）
    head3, neck3 = pts3d[0], pts3d[1]
    if any(v != 0.0 for v in head3) and any(v != 0.0 for v in neck3):
        d = math.dist(head3, neck3)
    else:
        d = 8.0
    if d < 1e-6:
        d = 8.0

    # 世界→像素的正交映射：用 2D/3D 同名点对拟合平移缩放（与导入端投影一致）
    pairs = [(pts3d[i], kps2d[i]) for i in alive]
    xs = sorted(pairs, key=lambda p: p[0][0])
    ys = sorted(pairs, key=lambda p: p[0][1])
    denom_x = xs[-1][0][0] - xs[0][0][0]
    denom_y = ys[-1][0][1] - ys[0][0][1]
    sx = (xs[-1][1][0] - xs[0][1][0]) / (denom_x or 1e-6)
    sy = (ys[-1][1][1] - ys[0][1][1]) / (denom_y or 1e-6)
    x0, y0 = xs[0][1][0], ys[0][1][1]

    def to_px(p3: tuple[float, float, float]) -> tuple[float, float]:
        # × SCALE：超采样画布上的像素坐标
        return ((x0 + (p3[0] - xs[0][0][0]) * sx) * SCALE,
                (y0 + (p3[1] - ys[0][0][1]) * sy) * SCALE)

    # 深度灰度：越近（z 越大，相机在 +Z）越亮，背景纯黑
    zmin = min(pts3d[i][2] for i in alive)
    zmax = max(pts3d[i][2] for i in alive)
    span = (zmax - zmin) or 1e-6

    def shade(z: float) -> int:
        return int(60 + 195 * max(0.0, min(1.0, (z - zmin) / span)))

    # 画家算法：基元（胶囊线段 / 头部球）按平均 z 从远到近绘制
    prims: list[tuple[float, list[float], int]] = []
    for a, b in LIMB_SEQ:
        ja, jb = a - 1, b - 1
        if ja not in alive or jb not in alive:
            continue
        pa, pb = pts3d[ja], pts3d[jb]
        za, zb = to_px(pa), to_px(pb)
        prims.append((
            (pa[2] + pb[2]) / 2,
            [za[0], za[1], zb[0], zb[1]],
            max(1, int(_limb_radius(ja, jb, d) * abs(sx) * SCALE)),
        ))
    if 0 in alive:
        zx, zy = to_px(head3)
        prims.append((
            head3[2] + d * 0.1,
            [zx, zy],
            max(1, int(RADIUS_HEAD * d * abs(sx) * SCALE)),
        ))
    for i in alive:
        if i == 0:
            continue
        jx, jy = to_px(pts3d[i])
        prims.append((
            pts3d[i][2],
            [jx, jy],
            max(1, int(RADIUS_LIMB * d * abs(sx) * SCALE)),
        ))

    prims.sort(key=lambda p: p[0])
    canvas = Image.new("L", (pose.canvas_width * SCALE, pose.canvas_height * SCALE), 0)
    draw = ImageDraw.Draw(canvas)
    for z, coords, r in prims:
        if len(coords) == 4:
            draw.line(coords, fill=shade(z), width=r)
        else:
            cx, cy = coords
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=shade(z))

    canvas = canvas.filter(ImageFilter.GaussianBlur(BLUR_RADIUS * SCALE))
    return canvas.resize((pose.canvas_width, pose.canvas_height), Image.LANCZOS).convert("L")


def render_depth_to_png(pose: PoseFile, output: str | Path, person_index: int = 0) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    render_depth(pose, person_index=person_index).save(output, format="PNG")
    return output

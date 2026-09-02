"""批量渲染：poses/ 下每个姿态 → 输出目录下同名 PNG。"""

from __future__ import annotations

from pathlib import Path

from .library import POSE_FILENAME, iter_pose_dirs
from .render import render_to_png
from .schema import load_pose


def batch_render(poses_dir: str | Path, output_dir: str | Path) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for pose_dir in iter_pose_dirs(poses_dir):
        pose = load_pose(pose_dir / POSE_FILENAME)
        outputs.append(render_to_png(pose, output_dir / f"{pose_dir.name}.png"))
    return outputs

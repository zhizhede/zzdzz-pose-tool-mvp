"""姿态资产库扫描与 index.yaml 维护。

约定：poses/ 下每个子目录是一个姿态单元，
pose.json（数值 ground truth）+ meta.yaml（描述/标签）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .schema import load_pose

POSE_FILENAME = "pose.json"
META_FILENAME = "meta.yaml"


def iter_pose_dirs(poses_dir: str | Path) -> list[Path]:
    poses_dir = Path(poses_dir)
    return sorted(p.parent for p in poses_dir.glob(f"*/{POSE_FILENAME}"))


def load_meta(pose_dir: Path) -> dict[str, Any]:
    meta_path = pose_dir / META_FILENAME
    if meta_path.exists():
        return yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    return {}


def build_index(poses_dir: str | Path) -> dict[str, Any]:
    entries = []
    for pose_dir in iter_pose_dirs(poses_dir):
        pose = load_pose(pose_dir / POSE_FILENAME)
        meta = load_meta(pose_dir)
        entries.append({
            "name": meta.get("name", pose_dir.name),
            "path": pose_dir.name,
            "description": meta.get("description", ""),
            "tags": sorted(meta.get("tags", [])),
            "canvas": [pose.canvas_width, pose.canvas_height],
            "people": len(pose.people),
        })
    return {"version": 1, "poses": entries}


def write_index(poses_dir: str | Path) -> Path:
    poses_dir = Path(poses_dir)
    out = poses_dir / "index.yaml"
    out.write_text(
        yaml.safe_dump(build_index(poses_dir), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return out

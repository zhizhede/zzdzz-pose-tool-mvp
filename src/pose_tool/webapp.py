"""FastAPI 后端：把 pose_tool 的业务函数暴露为本地 Web API。

安全边界：
- 默认只绑定 127.0.0.1，是本地单人工具
- 姿态名严格校验（防路径穿越）
- 识别的 API 密钥只在服务端读取 config.local.yaml，永不出现在 API 响应里
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .angles import compute_joint_angles
from .diff import diff_poses
from .library import POSE_FILENAME, build_index, iter_pose_dirs, load_meta
from .recognize import DEFAULT_CONFIG_PATH, swap_left_right
from .render import render_pose
from .schema import PoseFile, load_pose

ROOT = Path(__file__).resolve().parents[2]
POSES_DIR = ROOT / "poses"
WEBUI_DIST = ROOT / "webui" / "dist"

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class SavePoseBody(BaseModel):
    pose: PoseFile


class CreatePoseBody(BaseModel):
    name: str = Field(pattern=NAME_PATTERN.pattern)
    pose: PoseFile
    description: str = ""


class DiffBody(BaseModel):
    a: PoseFile
    b: PoseFile
    threshold_px: float = 2.0
    person_index: int = 0


def _pose_dir(name: str) -> Path:
    if not NAME_PATTERN.match(name):
        raise HTTPException(400, f"非法姿态名: {name!r}")
    return POSES_DIR / name


def create_app() -> FastAPI:
    app = FastAPI(title="zzdzz-pose-tool", docs_url="/api/docs")

    @app.get("/api/poses")
    def list_poses() -> dict[str, Any]:
        index = build_index(POSES_DIR)
        for entry in index["poses"]:
            entry["has_preview"] = (POSES_DIR / entry["path"] / "preview.png").exists()
        return index

    @app.get("/api/poses/{name}")
    def get_pose(name: str) -> dict[str, Any]:
        pose_dir = _pose_dir(name)
        pose_file = pose_dir / POSE_FILENAME
        if not pose_file.exists():
            raise HTTPException(404, f"姿态不存在: {name}")
        pose = load_pose(pose_file)
        return {"name": name, "meta": load_meta(pose_dir), "pose": pose.model_dump()}

    @app.get("/api/poses/{name}/preview")
    def get_preview(name: str) -> Response:
        preview = _pose_dir(name) / "preview.png"
        if not preview.exists():
            raise HTTPException(404, "预览图不存在")
        return FileResponse(preview, media_type="image/png")

    @app.put("/api/poses/{name}")
    def save_pose(name: str, body: SavePoseBody) -> dict[str, Any]:
        pose_dir = _pose_dir(name)
        pose_file = pose_dir / POSE_FILENAME
        if not pose_file.exists():
            raise HTTPException(404, f"姿态不存在（新建请用 POST）: {name}")
        pose_dir.mkdir(parents=True, exist_ok=True)
        pose_file.write_text(body.pose.model_dump_json(indent=2), encoding="utf-8")
        _regenerate_preview(pose_dir, body.pose)
        _rebuild_index()
        return {"ok": True}

    @app.post("/api/poses")
    def create_pose(body: CreatePoseBody) -> dict[str, Any]:
        pose_dir = _pose_dir(body.name)
        pose_file = pose_dir / POSE_FILENAME
        if pose_file.exists():
            raise HTTPException(409, f"姿态已存在: {body.name}")
        pose_dir.mkdir(parents=True, exist_ok=True)
        pose_file.write_text(body.pose.model_dump_json(indent=2), encoding="utf-8")
        (pose_dir / "meta.yaml").write_text(
            f"name: {body.name}\ndescription: {body.description}\ntags: []\n",
            encoding="utf-8",
        )
        _regenerate_preview(pose_dir, body.pose)
        _rebuild_index()
        return {"ok": True, "name": body.name}

    @app.post("/api/render")
    def render(body: PoseFile, person_index: int = 0) -> Response:
        img = render_pose(body, person_index=person_index)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")

    @app.post("/api/diff")
    def diff(body: DiffBody) -> dict[str, Any]:
        try:
            return diff_poses(body.a, body.b, threshold_px=body.threshold_px,
                              person_index=body.person_index)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/recognize/status")
    def recognize_status() -> dict[str, Any]:
        from .recognize import load_recognize_config

        try:
            config = load_recognize_config(ROOT / DEFAULT_CONFIG_PATH)
            return {"configured": True, "model": config["model"]}
        except (FileNotFoundError, ValueError):
            return {"configured": False, "model": None}

    @app.post("/api/recognize")
    async def recognize(
        image: UploadFile = File(...),
        swap: bool = Form(False),
    ) -> dict[str, Any]:
        from .recognize import load_recognize_config, recognize_image

        try:
            config = load_recognize_config(ROOT / DEFAULT_CONFIG_PATH)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(400, str(e))
        raw = await image.read()
        suffix = Path(image.filename or "upload.png").suffix or ".png"
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            upload = Path(td) / f"upload{suffix}"
            upload.write_bytes(raw)
            pose = recognize_image(upload, config, swap_sides=swap)
        return {"pose": pose.model_dump(), "angles": compute_joint_angles(pose)}

    @app.delete("/api/poses/{name}")
    def delete_pose(name: str) -> dict[str, Any]:
        import shutil

        pose_dir = _pose_dir(name)
        if not pose_dir.exists():
            raise HTTPException(404, f"姿态不存在: {name}")
        shutil.rmtree(pose_dir)
        _rebuild_index()
        return {"ok": True}

    # ---- 前端静态托管（已构建的 webui/dist；不存在则只提供 API） ----
    if WEBUI_DIST.exists():
        app.mount("/", StaticFiles(directory=WEBUI_DIST, html=True), name="webui")
    else:
        @app.get("/")
        def no_frontend() -> JSONResponse:
            return JSONResponse({"hint": "前端未构建：cd webui && npm install && npm run build"})

    return app


def _regenerate_preview(pose_dir: Path, pose: PoseFile) -> None:
    render_pose(pose).save(pose_dir / "preview.png", format="PNG")


def _rebuild_index() -> None:
    from .library import write_index

    write_index(POSES_DIR)

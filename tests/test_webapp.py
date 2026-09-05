"""Web API 冒烟测试（TestClient，不起真实端口）。"""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pose_tool.webapp import create_app

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "poses" / "looking-down-phone" / "pose.json"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """把 poses 目录指向临时副本，避免测试污染真实资产库。"""
    import shutil

    fake_poses = tmp_path / "poses"
    shutil.copytree(ROOT / "poses", fake_poses)
    monkeypatch.setattr("pose_tool.webapp.POSES_DIR", fake_poses)
    import pose_tool.webapp as webapp

    app = create_app()
    return TestClient(app), fake_poses


def test_list_poses(client):
    c, _ = client
    data = c.get("/api/poses").json()
    assert any(p["name"] == "looking-down-phone" for p in data["poses"])


def test_get_pose(client):
    c, _ = client
    data = c.get("/api/poses/looking-down-phone").json()
    assert len(data["pose"]["people"][0]["pose_keypoints_2d"]) == 54


def test_get_pose_rejects_path_traversal(client):
    c, _ = client
    assert c.get("/api/poses/..%2F..%2Fetc").status_code in (400, 404)


def test_get_preview_png(client):
    c, _ = client
    r = c.get("/api/poses/looking-down-phone/preview")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_update_pose_regenerates_preview(client):
    c, poses_dir = client
    pose = c.get("/api/poses/looking-down-phone").json()["pose"]
    pose["people"][0]["pose_keypoints_2d"][1] = 190.0  # nose.y 改动
    r = c.put("/api/poses/looking-down-phone", json={"pose": pose})
    assert r.status_code == 200
    saved = (poses_dir / "looking-down-phone" / "pose.json").read_text(encoding="utf-8")
    assert "190.0" in saved


def test_create_and_conflict(client):
    c, poses_dir = client
    pose = c.get("/api/poses/looking-down-phone").json()["pose"]
    body = {"name": "test-pose", "pose": pose, "description": "测试"}
    assert c.post("/api/poses", json=body).status_code == 200
    assert c.post("/api/poses", json=body).status_code == 409
    assert (poses_dir / "test-pose" / "pose.json").exists()


def test_create_rejects_bad_name(client):
    c, _ = client
    pose = c.get("/api/poses/looking-down-phone").json()["pose"]
    body = {"name": "../evil", "pose": pose}
    assert c.post("/api/poses", json=body).status_code == 422


def test_render_endpoint_returns_png(client):
    c, _ = client
    pose = c.get("/api/poses/looking-down-phone").json()["pose"]
    r = c.post("/api/render", json=pose)
    assert r.headers["content-type"] == "image/png"
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (512, 512)


def test_diff_endpoint(client):
    c, _ = client
    pose = c.get("/api/poses/looking-down-phone").json()["pose"]
    other = {**pose, "people": [{**pose["people"][0]}]}
    other["people"][0]["pose_keypoints_2d"] = list(pose["people"][0]["pose_keypoints_2d"])
    other["people"][0]["pose_keypoints_2d"][1] = 220.0
    report = c.post("/api/diff", json={"a": pose, "b": other}).json()
    assert report["summary"]["moved_count"] >= 1


def test_recognize_status_no_leak(client, monkeypatch):
    c, _ = client
    data = c.get("/api/recognize/status").json()
    assert set(data) == {"configured", "model"}
    assert "sk-" not in str(data)


def test_reference_upload_and_gen_command(client):
    """参考图上传后，生成命令自动带上 --reference 与缓存的 MiniMax 提示词。"""
    c, poses_dir = client
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 100, 50)).save(buf, format="PNG")
    r = c.post("/api/poses/looking-down-phone/reference",
               files={"file": ("ref.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200
    assert (poses_dir / "looking-down-phone" / "reference.png").exists()

    # 预置缓存提示词 → 走 minimax-cached 分支，不发网络请求
    (poses_dir / "looking-down-phone" / "prompt.txt").write_text(
        "a woman in a red dress", encoding="utf-8")
    data = c.post("/api/gen-command",
                  json={"name": "looking-down-phone", "use_minimax": True}).json()
    assert data["reference"] is True
    assert data["prompt_source"] == "minimax-cached"
    assert data["prompt"] == "a woman in a red dress"
    assert "--pose poses/looking-down-phone/preview.png" in data["command"]
    assert '--reference "poses/looking-down-phone/reference.png"' in data["command"]


def test_gen_command_without_reference_uses_rule(client):
    c, _ = client
    data = c.post("/api/gen-command",
                  json={"name": "looking-down-phone", "use_minimax": False}).json()
    assert data["reference"] is False
    assert data["prompt_source"] == "rule"
    assert "--reference" not in data["command"]
    assert data["prompt"].startswith("a person with ")
    assert "--pose poses/looking-down-phone/preview.png" in data["command"]


def test_gen_command_unknown_pose(client):
    r = c = None
    c, _ = client
    assert c.post("/api/gen-command", json={"name": "no-such-pose"}).status_code == 404


def test_reference_upload_rejects_bad_name(client):
    c, _ = client
    # 空格不匹配 NAME_PATTERN；../ 会被 HTTP 客户端规范化掉，改用非法字符验证
    r = c.post("/api/poses/bad%20name/reference",
               files={"file": ("x.png", b"x", "image/png")})
    assert r.status_code == 400

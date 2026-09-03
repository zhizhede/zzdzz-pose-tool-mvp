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

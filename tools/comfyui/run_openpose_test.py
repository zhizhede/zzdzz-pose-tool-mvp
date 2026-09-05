"""向本地 ComfyUI 提交 ControlNet-OpenPose 工作流并取回生成图。

用法（ComfyUI 已在 8188 端口运行）:
    python tools/comfyui/run_openpose_test.py \
        --pose poses/sitting/preview.png \
        --comfyui-root E:/Program/zzdzz-ai/ComfyUI_windows_portable/ComfyUI \
        --out outputs/acceptance3

脚本职责:
1. 把骨架 PNG 拷入 ComfyUI/input/（LoadImage 只能读该目录）
2. 替换工作流中的图片名/正向提示词后 POST /prompt
3. 轮询 /history 直到完成，经 /view 下载输出到 --out 目录

仅用标准库，不引入新依赖。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

WORKFLOW_PATH = Path(__file__).with_name("workflow_openpose_api.json")

# 2D 骨架表达不了正/背面，朝向必须靠提示词；按 pose.json 的 facing 自动补
FACING_PROMPT = {
    "front": "facing the camera, front view",
    "back": "viewed from behind, back view",
    "profile": "side view, profile",
}


def auto_facing_prompt(pose_path: Path) -> str:
    """读骨架图同目录的 pose.json，返回 facing 对应的提示词片段（无则空串）。"""
    pose_json = pose_path.with_name("pose.json")
    if not pose_json.exists():
        return ""
    try:
        data = json.loads(pose_json.read_text(encoding="utf-8"))
        facing = (data.get("people") or [{}])[0].get("facing")
        return FACING_PROMPT.get(facing, "")
    except (json.JSONDecodeError, OSError):
        return ""


def _http_json(base: str, path: str, payload: dict | None = None) -> dict:
    url = base + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"[!] ComfyUI 拒绝请求（{e.code}）：{body[:1500]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pose", required=True, help="骨架 PNG 路径（如 poses/sitting/preview.png）")
    ap.add_argument("--comfyui-root", required=True, help="ComfyUI 数据目录（含 input/ output/）")
    ap.add_argument("--out", required=True, help="生成图保存目录")
    ap.add_argument("--prompt", default=None, help="正向提示词（默认用工作流内置）")
    ap.add_argument("--no-auto-facing", action="store_true",
                    help="不按 pose.json 的 facing 自动追加朝向提示词")
    ap.add_argument("--no-depth", action="store_true",
                    help="不使用深度图双控（即使 pose 目录里有 preview_depth.png）")
    ap.add_argument("--depth-strength", type=float, default=0.7, help="深度 ControlNet 强度")
    ap.add_argument("--reference", default=None,
                    help="角色参考图路径：启用 IP-Adapter 身份锁定，生成同一个人")
    ap.add_argument("--identity-weight", type=float, default=0.8, help="IP-Adapter 强度")
    ap.add_argument("--strength", type=float, default=1.0, help="骨架 ControlNet 强度")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--host", default="http://127.0.0.1:8188")
    args = ap.parse_args()

    pose_path = Path(args.pose)
    root = Path(args.comfyui_root)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 深度图双控：骨架图同目录存在 preview_depth.png 时自动启用
    depth_path = pose_path.with_name("preview_depth.png")
    use_depth = depth_path.exists() and not args.no_depth
    # 身份锁定：提供 --reference 时启用 IP-Adapter
    ref_path = Path(args.reference) if args.reference else None
    use_identity = ref_path is not None
    if use_identity and not ref_path.exists():
        print(f"[!] 参考图不存在：{ref_path}，忽略身份锁定")
        use_identity = False
    if use_identity:
        workflow_path = Path(__file__).with_name("workflow_identity_api.json")
        if use_depth:
            workflow_path = Path(__file__).with_name("workflow_identity_depth_api.json")
    elif use_depth:
        workflow_path = Path(__file__).with_name("workflow_openpose_depth_api.json")
    else:
        workflow_path = WORKFLOW_PATH

    input_name = "sitting_pose.png"
    shutil.copyfile(pose_path, root / "input" / input_name)
    depth_name = None
    if use_depth:
        depth_name = "depth_map.png"
        shutil.copyfile(depth_path, root / "input" / depth_name)
        print(f"[i] 深度双控启用：{depth_path.name}（depth strength={args.depth_strength}）")
    ref_name = None
    if use_identity:
        ref_name = "reference.png"
        shutil.copyfile(ref_path, root / "input" / ref_name)
        print(f"[i] 身份锁定启用：{ref_path.name}（identity weight={args.identity_weight}）")

    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))

    # 按节点类型定位（不依赖具体节点编号，各工作流通用）
    def nodes_of(cls):
        return sorted((nid for nid, n in workflow.items() if n["class_type"] == cls), key=int)

    load_images = nodes_of("LoadImage")  # 各工作流内 LoadImage 按声明顺序=骨架、深度(如有)、参考(如有)
    targets = [input_name]
    if depth_name:
        targets.append(depth_name)
    if ref_name:
        targets.append(ref_name)
    assert len(load_images) == len(targets), "工作流 LoadImage 数量与控制图不匹配"
    for nid, name in zip(load_images, targets):
        workflow[nid]["inputs"]["image"] = name
    applies = nodes_of("ControlNetApply")
    workflow[applies[0]]["inputs"]["strength"] = args.strength
    if depth_name and len(applies) > 1:
        workflow[applies[1]]["inputs"]["strength"] = args.depth_strength
    if use_identity:
        ipa = nodes_of("IPAdapterAdvanced")
        if ipa:
            workflow[ipa[0]]["inputs"]["weight"] = args.identity_weight
    encodes = nodes_of("CLIPTextEncode")
    prompt = args.prompt or workflow[encodes[0]]["inputs"]["text"]
    if not args.no_auto_facing:
        extra = auto_facing_prompt(pose_path)
        if extra and extra not in prompt:
            prompt = f"{prompt}, {extra}"
            print(f"[i] 已按 pose.json 的 facing 自动追加朝向提示词: {extra}")
    workflow[encodes[0]]["inputs"]["text"] = prompt
    workflow[nodes_of("KSampler")[0]]["inputs"]["seed"] = args.seed

    queued = _http_json(args.host, "/prompt", {"prompt": workflow})
    prompt_id = queued["prompt_id"]
    print(f"[1/3] 已入队 prompt_id={prompt_id}")

    deadline = time.time() + 600  # 4GB 显存 + lowvram 首次加载模型可能要几分钟
    while time.time() < deadline:
        history = _http_json(args.host, f"/history/{prompt_id}")
        if prompt_id in history:
            entry = history[prompt_id]
            if entry.get("status", {}).get("completed"):
                break
            if entry.get("status", {}).get("status_str") == "error":
                print("[!] 生成失败:", json.dumps(entry["status"], ensure_ascii=False)[:2000])
                return 1
        time.sleep(3)
    else:
        print("[!] 超时（600s）未完成")
        return 1

    outputs = history[prompt_id]["outputs"]
    saved = []
    for node_out in outputs.values():
        for img in node_out.get("images", []):
            q = urllib.parse.urlencode({
                "filename": img["filename"],
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output"),
            })
            url = f"{args.host}/view?{q}"
            dest = out_dir / img["filename"]
            with urllib.request.urlopen(url, timeout=60) as resp, open(dest, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            saved.append(dest)
            print(f"[2/3] 已下载 {dest}")

    if not saved:
        print("[!] 队列完成但没有输出图片")
        return 1
    print(f"[3/3] 完成：{len(saved)} 张图 → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

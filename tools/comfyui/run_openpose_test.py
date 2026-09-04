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


def _http_json(base: str, path: str, payload: dict | None = None) -> dict:
    url = base + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pose", required=True, help="骨架 PNG 路径（如 poses/sitting/preview.png）")
    ap.add_argument("--comfyui-root", required=True, help="ComfyUI 数据目录（含 input/ output/）")
    ap.add_argument("--out", required=True, help="生成图保存目录")
    ap.add_argument("--prompt", default=None, help="正向提示词（默认用工作流内置）")
    ap.add_argument("--strength", type=float, default=1.0, help="ControlNet 强度")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--host", default="http://127.0.0.1:8188")
    args = ap.parse_args()

    pose_path = Path(args.pose)
    root = Path(args.comfyui_root)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_name = "sitting_pose.png"
    shutil.copyfile(pose_path, root / "input" / input_name)

    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    workflow["5"]["inputs"]["image"] = input_name
    workflow["6"]["inputs"]["strength"] = args.strength
    workflow["7"]["inputs"]["seed"] = args.seed
    if args.prompt:
        workflow["2"]["inputs"]["text"] = args.prompt

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

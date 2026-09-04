# ComfyUI 本地 ControlNet-OpenPose 生成链路

控制层（骨架 PNG → ControlNet → 真实人像）的本地验证/生产环境。
零训练，纯推理：SD1.5 底模（DreamShaper 8）+ ControlNet v11p OpenPose。

## 目录约定（本机）

| 路径 | 用途 |
| --- | --- |
| `E:/Program/zzdzz-ai/` | 安装根目录（下载的 7z 与模型 .safetensors/.pth） |
| `E:/Program/zzdzz-ai/ComfyUI_windows_portable/` | ComfyUI portable 解压结果 |
| `<portable>/ComfyUI/models/checkpoints/` | 放 `DreamShaper_8_pruned.safetensors` |
| `<portable>/ComfyUI/models/controlnet/` | 放 `control_v11p_sd15_openpose.pth` |

## 启动（4GB 显存必须带 --lowvram）

```bat
cd /d E:\Program\zzdzz-ai\ComfyUI_windows_portable
run_nvidia_gpu.bat --lowvram --port 8188
```

浏览器访问 http://127.0.0.1:8188 确认启动成功（API 模式无需打开 UI）。

## 跑验收测试 #3（坐姿）

```bash
python tools/comfyui/run_openpose_test.py \
    --pose poses/sitting/preview.png \
    --comfyui-root "E:/Program/zzdzz-ai/ComfyUI_windows_portable/ComfyUI" \
    --out outputs/acceptance3
```

脚本自动完成：拷骨架图入 `ComfyUI/input/` → 提交工作流 → 轮询 → 下载成图。
产出与 `poses/sitting/preview.png` 并排对照，判断生成人是否为坐姿、关节是否对位。

## 换 pose 批量生成

`run_openpose_test.py --pose <任意 preview.png> --seed <n> --prompt "<场景>"`
即构成确定性生成入口：同一 pose.json → 同一骨架 PNG → 同一 seed = 同一张图。

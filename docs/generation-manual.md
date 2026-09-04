# 全流程图像生成操作手册

> pose.json（数值层）→ 骨架 PNG（渲染层）→ ControlNet 真实人像（生成层）。
> 全程无图像识别介入，同 pose + 同 seed = 同一张图，确定性可复现。

---

## 一分钟上手（真实案例）

**目标**：把 `poses/sitting`（坐姿）变成一张真实感图片。

前提：两个服务已启动（见 [前置条件](#三前置条件)，日常只需启动一次）。

**① 启动生成引擎**（ComfyUI，如果还没开）：

```bat
E:\Program\zzdzz-ai\start_comfyui.bat
```

**② 打开姿势编辑器**：浏览器访问 <http://127.0.0.1:7860>，选一个姿势（或编辑/导入一个），点工具栏「下载骨架 PNG（喂 ControlNet）」拿到骨架图——也可以直接用仓库里现成的 `poses/sitting/preview.png`。

**③ 一条命令生成**（项目根目录下，PowerShell 整行粘贴）：

```powershell
python tools/comfyui/run_openpose_test.py --pose poses/sitting/preview.png --comfyui-root "E:/Program/zzdzz-ai/ComfyUI" --out "C:\Users\ZZDZZ\Downloads" --prompt "a woman in a white shirt sitting on a chair, office background, photorealistic" --seed 42
```

**④ 看结果**：约 20-60 秒后，图出现在 `C:\Users\ZZDZZ\Downloads\openpose_test_XXXXX_.png`。

> 已验证案例：`sitting` 骨架 → 森林坐木人像；`looking-down-phone` 骨架 → 城市阳台低头持机人像。姿势 100% 由骨架决定，prompt 只管场景/人物/画风。

**就这三样东西**：姿势文件（preview.png）、生成引擎（8188 端口）、一条命令。
想换姿势就换 `--pose`，想换画面就换 `--prompt`，想出不同人就换 `--seed`。

---

## 前置条件

| 组件 | 端口 | 启动方式 | 用途 |
| --- | --- | --- | --- |
| pose-tool WebUI | 7860 | `python -m uvicorn pose_tool.webapp:create_app --factory --port 7860` | 编辑/导入/管理姿势 |
| ComfyUI | 8188 | `E:\Program\zzdzz-ai\start_comfyui.bat` | 骨架 → 真实人像生成 |

验证就绪：浏览器打开对应端口有页面即可；ComfyUI 也可以 `curl http://127.0.0.1:8188/system_stats`。

## 获得姿势的三种方式（WebUI 内）

1. **导入 3D 动作**（推荐）：「导入」选 Mixamo 下载的 `.dae` → 选帧 → 保存。系统按真实人体比例投影（190cm 画布、地面锚定），坐/站高度线索保留。
2. **手动编辑**：新建空白 T-pose → 拖动 18 个关键点（面板实时显示关节角度）→「另存为」。
3. **导入 JSON**：OpenPose JSON 或 COCO JSON 直接导入。

保存后自动入库到 `poses/<名字>/`：

```
poses/<名字>/
├── pose.json    # 数值层：54 个浮点数，可 diff 可版本管理
├── preview.png  # 骨架图：ControlNet 的直接输入
└── meta.yaml    # 名称/描述/标签
```

## 生成命令参数详解

```
python tools/comfyui/run_openpose_test.py --pose <骨架PNG> --comfyui-root <ComfyUI目录> --out <输出目录> [可选项]
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--pose` | ✅ | 骨架 PNG 路径（通常是 `poses/<名字>/preview.png`） |
| `--comfyui-root` | ✅ | 固定填 `E:/Program/zzdzz-ai/ComfyUI` |
| `--out` | ✅ | **输出目录**（不是文件名！），图自动命名写入 |
| `--prompt` | | 正向提示词：场景、人物、光线、画风。姿势不归它管 |
| `--strength` | | ControlNet 强度，默认 `1.0`。降低可让 AI 更自由（姿势可能漂移） |
| `--seed` | | 随机种子。固定 = 可复现；换 = 同姿势不同人 |
| `--host` | | ComfyUI 地址，默认 `http://127.0.0.1:8188` |

**prompt 写法建议**：`主体 + 姿势一致的场景描述 + 光线/画风`。
例：`"a man in a suit sitting on a park bench, autumn, golden hour, photorealistic"`。

## 确定性复现与批量出图

- **复现**：同一 `pose.json` 渲染的骨架 + 同一 seed → 逐像素一致。pose.json 提交 git 后，任何人任何机器都能重新生成同一张图——这就是"姿势即程序"。
- **同一姿势出 N 个人**：固定 `--pose`，循环换 `--seed 1 2 3...`
- **批量换姿势**：循环 `--pose`（夜间跑，4G 显存单张 20-60 秒）

PowerShell 批量示例：

```powershell
foreach ($s in 1,2,3) { python tools/comfyui/run_openpose_test.py --pose poses/sitting/preview.png --comfyui-root "E:/Program/zzdzz-ai/ComfyUI" --out "outputs/batch" --seed $s }
```

## 进阶：改工作流

生成管线定义在 `tools/comfyui/workflow_openpose_api.json`（CheckpointLoaderSimple → CLIP 编码 → ControlNetApply → KSampler → SaveImage）。常见改动：

- 换底模：把新 `.safetensors` 放进 `E:/Program/zzdzz-ai/ComfyUI/models/checkpoints/`，改节点 `1` 的 `ckpt_name`
- 换采样器/步数：改节点 `7` 的 `sampler_name` / `steps`
- 出竖版图：改节点 `8` 的 `width`/`height`（骨架是 512×512，等比放大效果最稳）

也可以打开 <http://127.0.0.1:8188> 可视化调试，再用 `POST /prompt` 提交。

## 故障排查

| 现象 | 原因与处理 |
| --- | --- |
| `connection refused` / 入队无响应 | ComfyUI 没启动 → 跑 `start_comfyui.bat`，看到 `To see the GUI...` 再执行命令 |
| `OSError: [Errno 22] Invalid argument` | 服务端输出管道被截断（外部托管启动方式的坑）→ 重启 ComfyUI 即恢复 |
| PowerShell 报 `Missing expression after unary operator '--'` | 把 Bash 的 `\` 换行命令整段贴进了 PowerShell → 用单行命令，或用反引号 `` ` `` 续行 |
| 图生成了但姿势不对 | 检查 `--pose` 是否指向正确的 preview.png；`--strength` 不要低于 0.8；prompt 里不要写与姿势冲突的词（如骨架是坐姿却写 standing） |
| `the following arguments are required` | 参数没传全，或多行命令被 PowerShell 拆散（同上，用单行） |
| 生成很慢（>2 分钟/张） | 显存被其他程序占用；关掉占显存的应用后重启 ComfyUI |

## 环境资产一览

| 路径 | 内容 |
| --- | --- |
| `E:\Program\zzdzz-ai\ComfyUI\` | ComfyUI v0.3.43（gitee 源码安装） |
| `E:\Program\zzdzz-ai\ComfyUI-env\` | 专用 venv（torch 2.5.1+cu121，CUDA 可用） |
| `E:\Program\zzdzz-ai\ComfyUI\models\checkpoints\` | DreamShaper 8（SD1.5 底模） |
| `E:\Program\zzdzz-ai\ComfyUI\models\controlnet\` | ControlNet v11p OpenPose（fp16） |
| `E:\Program\zzdzz-ai\start_comfyui.bat` | 一键启动（`--lowvram`，适配 4G 显存） |
| `tools/comfyui/` | 工作流 JSON + 生成驱动脚本 + robust 下载脚本 |

# 全流程图像生成操作手册

> pose.json（数值层）→ 骨架 PNG（渲染层）→ ControlNet 真实人像（生成层）。
> 全程无图像识别介入，同 pose + 同 seed = 同一张图，确定性可复现。

---

## 一分钟上手（真实案例）

**目标**：把 `poses/sitting`（坐姿）变成一张真实感图片。

前提：两个服务已启动（见 [前置条件](#三前置条件)，日常只需启动一次）。

**① 启动前置服务**（ComfyUI + 姿势编辑器，已在运行的会自动跳过）：

```bat
tools\start-all.bat
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

**一键启动（推荐）**：双击 `tools\start-all.bat`，或在终端运行它。脚本自动检测并拉起两个服务（已在运行的跳过，可重复执行），全部就绪后显示 `ALL READY`：

- ComfyUI 日志：`E:\Program\zzdzz-ai\comfyui.log`（启动失败先看这里）
- 结束方式：关闭脚本拉起的两个最小化控制台窗口

也可分别手动启动：

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
| `--prompt` | | 正向提示词：场景、人物、光线、画风。姿势与朝向不归它管（朝向按 pose.json 的 facing 自动追加） |
| `--depth-strength` | | 深度 ControlNet 强度，默认 `0.7`（有深度图时生效） |
| `--no-depth` | | 强制不用深度双控 |
| `--strength` | | ControlNet 强度，默认 `1.0`。降低可让 AI 更自由（姿势可能漂移） |
| `--seed` | | 随机种子。固定 = 可复现；换 = 同姿势不同人 |
| `--host` | | ComfyUI 地址，默认 `http://127.0.0.1:8188` |

**prompt 写法建议**：`主体 + 姿势一致的场景描述 + 光线/画风`。
例：`"a man in a suit sitting on a park bench, autumn, golden hour, photorealistic"`。

## 深度双控（openpose + depth）

骨架图表达"关节在哪"，深度图表达"前后关系"——两者叠加是结构控制的最强组合：

- **深度图来源**：pose.json 的 `pose_keypoints_3d` 字段（DAE 导入时的 3D 关节真值），渲染为 `preview_depth.png`（近亮远暗，与骨架图逐像素对位）
- **自动启用**：生成脚本检测到骨架图同目录有 `preview_depth.png` 就自动走双控工作流（无需改命令）；`--no-depth` 可关闭，`--depth-strength`（默认 0.7）调节深度约束强度
- **解决的问题**：四肢前后遮挡（跷二郎腿哪条腿在前）、身体转角（侧身 45°）、肢体交叠层次、透视缩短——这些是 2D 骨架在原理上无法表达的
- 手动渲染深度图：`python -m pose_tool.cli render poses/<名字>/pose.json --output preview_depth.png --depth`

实测对比（同命令同 seed）：单骨架时腿部姿态常有自由发挥；深度双控后小腿交叠的层次与数据一致。

## 朝向控制（正/背面）

2D 骨架图**无法表达正面/背面**——同一个人面向镜头和背对镜头，18 个关键点的平面位置几乎一样。朝向必须靠提示词补充，系统已经帮你做了大半：

- **DAE 导入时自动判定朝向**：利用 3D 骨骼数据算出 `facing` 字段（`front`/`back`/`profile`），写入 pose.json，导入警告里也会提示
- **WebUI 生图指令自动带朝向词**：「复制生图指令」会根据 facing 自动追加"朝向要求"（如 `facing the camera, front view`），复制后直接用即可
- **CLI 生成脚本自动注入**：`run_openpose_test.py` 检测到骨架图同目录有 pose.json 时，自动把朝向提示词追加到正向提示词末尾（`--no-auto-facing` 可关闭）

| facing | 建议提示词 |
| --- | --- |
| `front` | `facing the camera, front view` |
| `back` | `viewed from behind, back view` |
| `profile` | `side view, profile` |
| （无字段） | 按场景自行指定，避免模型随机选择朝向 |

实测结论（同骨架同 seed 只改朝向词）：`front view` → 正面坐姿；`back view` → 背面伏案。朝向词是朝向的主控信号；骨架图中的五官点（背面时自动隐藏）为辅助信号。

## 动作图片识别（DWPose 本地）

输入一张动作图片，本地识别出 18 点关键点生成 pose.json——"动作图片 → 动作数据"的入口：

```bash
python -m pose_tool.cli pose-detect 动作图片.jpg --output poses/my-pose/pose.json
```

WebUI 的「导入」直接选图片（jpg/png/webp）也可以。

**能力边界（如实）**：

- 识别的是**精确 2D 关键点**（DWPose，亚像素级），与早期 MiniMax 语义级识别（粗糙、会左右翻）不同
- 单张图片**没有 3D 深度**——此类资产无 pose_keypoints_3d，不能导 BVH/深度图，朝向未知
- 多人图片暂不支持（官方 yolox 人体检测器上传损坏，缺失时自动整图回退，仅单人居中图片可靠）
- 模型位置：`E:/Program/zzdzz-ai/models/dwpose/`（dw-ll_ucoco_384.onnx + yolox_l.onnx）

## 导出 BVH（送进 Blender / Unity）

pose.json 的 3D 关节真值可以导出为 BVH 格式——Blender、Unity 及多数 3D 软件原生支持：

```bash
python -m pose_tool.cli export-bvh poses/sitting/pose.json --output sitting.bvh
```

- 导出的骨架**已摆好该姿势**（姿势携带在 rest 骨架里，旋转通道为 0），导入 3D 软件即见姿势
- Blender：File → Import → Motion Capture (.bvh)；Unity：拖入项目后用 Skeleton 代理解析
- 坐标系 y-up、单位厘米（Mixamo 惯例）；Blender 导入时轴向选 Y-up
- 仅 DAE 导入的资产携带 3D 数据（可导 BVH）；识别 JSON 导入的 2D 资产不支持

## 身份锁定（同一角色）

只控姿势不控身份时，每次生成的都是不同的人。加 `--reference` 指定角色参考图后，系统走 IP-Adapter 身份锁定，生成"参考图里这个人"执行指定姿势：

```powershell
python tools/comfyui/run_openpose_test.py --pose poses/sitting/preview.png --comfyui-root "E:/Program/zzdzz-ai/ComfyUI" --out "outputs" --reference "角色参考图.png" --prompt "..." --seed 42
```

- `--identity-weight`（默认 0.8）：参考图相貌的保持强度；调低则更像提示词描述的人
- 参考图建议：单人、清晰、构图干净；半身或全身皆可
- 实测：同一参考图 + 不同姿势（站立/坐姿），人物相貌、发型、着装风格保持一致

**模型文件健康检查**：镜像源上出现过"文件头合法但权重里散布 NaN"的坏副本（CLIP-ViT-H 编码器曾中招，表现为生成全黑图）。下载任何 .safetensors 模型后先扫描再入库：

```bash
python tools/comfyui/scan_safetensors.py <文件.safetensors>
```

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
| 生成人物朝向随机（正面/背面不定） | 2D 骨架不含朝向 → 看 pose.json 的 `facing` 字段，把对应朝向词加进 prompt（见「朝向控制」） |
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

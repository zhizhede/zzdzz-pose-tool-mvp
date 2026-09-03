# zzdzz-pose-tool

把姿态从 AI 生图里的随机不可控效果，变成**可编辑、可保存、可 Diff、可批量、确定性复现**的工程资产。

核心思路：姿态的 ground truth 是**结构化数值**（pose.json），骨架图只是渲染产物——不经过任何图像识别，因此没有 DWPose 的噪声、丢点、漂移问题。

## 安装

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"   # Windows
# .venv/bin/pip install -e ".[dev]"     # Linux/macOS
```

## 姿态资产约定

```
poses/
├── index.yaml                    # 库索引（pose index 重建）
└── looking-down-phone/           # 一个姿态单元一个目录
    ├── pose.json                 # 数值 ground truth（OpenPose COCO-18 兼容）
    ├── meta.yaml                 # 名称、描述、标签
    └── preview.png               # 渲染预览（可再生成，建议提交）
```

`pose.json` 格式与 openpose-editor / ControlNet-OpenPose 生态兼容：body 固定 18 点，手 21×2、脸 70 点可选，全部为 `[x, y, conf]` 扁平数组，`conf <= 0` 表示缺失。JSON Schema 由 `pose schema` 从 pydantic 模型导出。

## 命令

```bash
pose render poses/looking-down-phone/pose.json -o renders/looking-down-phone.png
pose diff  poses/a/pose.json poses/b/pose.json          # 语义 diff：人可读的变化报告
pose batch poses/ -o renders/                           # 批量渲染全库
pose index poses/                                       # 重建 index.yaml
pose schema                                             # 导出 schemas/pose.schema.json
```

## 渲染保真度

骨架图的颜色表、肢体连接、线宽、模糊参数与 `controlnet_aux.util.draw_bodypose` 一致——ControlNet-OpenPose 是在这套视觉分布上训练的。

## AI 识图：从图片提取姿态

用视觉大模型（MiniMax 等，OpenAI 兼容接口）识别图片中的人物姿态，导出 pose.json 与骨骼角度：

```bash
cp config.example.yaml config.local.yaml   # 填入 API 密钥（此文件被 .gitignore 排除，永不入库）
pose recognize photo.png -o poses/from-photo/pose.json --angles-out angles.json
```

左右约定与已知限制：

- 本项目 pose.json 统一采用**观察者视角**左右约定（画面左侧 = `left_*`）
- MLLM 对骨架/剪影类图片会系统性颠倒左右——目视确认后加 `--swap-left-right` 重新识别或对已有结果调用 `pose_tool.recognize.swap_left_right` 修正
- 识别结果是**草稿**（实测髋/膝误差 5~15px，手臂 25~60px，头部簇可达 60px），入库前建议 `pose render` 目视核对并微调

## Web 界面

```bash
pose web          # http://127.0.0.1:7860（仅监听本机）
```

四个功能区：**姿态库**（列表/搜索/预览）、**编辑器**（画布拖拽关键点、实时关节角度、保存自动重渲预览）、**AI 识图**（上传图片→模型识别→微调→入库）、**对比**（双画布 + 语义 diff 报告）。

- 前端源码在 `webui/`（Vue 3 + Vite + TS）；构建产物 `webui/dist` 已入库，Python 用户免 Node
- 改前端：`cd webui && npm install && npm run dev`（/api 代理到 7860）
- 识别密钥只在服务端 `config.local.yaml`，浏览器与 API 响应均不可见

## 测试

```bash
.venv/Scripts/python -m pytest -q
```

关键回归项：同输入渲染 PNG **逐字节一致**（确定性复现）。

## 文档

- [调研报告（2026-09-02）](docs/research/2026-09-02-pose-pipeline-survey.md)
- [样例设计说明（早期探索版）](samples/README.md)

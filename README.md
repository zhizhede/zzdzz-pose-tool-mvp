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

## 测试

```bash
.venv/Scripts/python -m pytest -q
```

关键回归项：同输入渲染 PNG **逐字节一致**（确定性复现）。

## 文档

- [调研报告（2026-09-02）](docs/research/2026-09-02-pose-pipeline-survey.md)
- [样例设计说明（早期探索版）](samples/README.md)

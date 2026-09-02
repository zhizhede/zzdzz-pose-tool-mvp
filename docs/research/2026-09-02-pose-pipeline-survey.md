# AI 小说 / 图像生成的姿态工程化调研（2026-09-02）

> 调研目的：把"姿态"从 AI 生图里的随机不可控效果，转变为**可编辑、可保存、可 Diff、可批量、确定性复现**的工程资产。
>
> 调研范围：在线摆姿 SaaS、DWPose 识别、Blender 工程化、SMPL-X/VRM/VRMA 资产层、动作迁移、AI 生图/生视频模型的姿态输入接口。
>
> ⚠️ 本报告由 3 个并行 agent（general-purpose）独立完成，URL 来自 agent 的实时联网采样（2026-09-02 当日）。本会话本地网络出口被屏蔽，无法二次核验 star/commit 时间，请人工打开 URL 看一眼 README 再做 fork 决策。

---

## 0. 用户原判断的事实校验

| 原判断 | 事实校验 | 结论 |
|---|---|---|
| Posemy / MagicPoser 黑盒 + 角度不可读 + 导出受限 | 三份报告一致，无反证 | **成立** |
| DWPose 噪声 / 丢点 / 漂移 | 单帧可用、时序不可用 | **部分成立** |
| Blender 强但难产纯姿态参数 | .blend 不 Git 友好，但**导出层成熟** | **成立但有解** |
| "动作迁移只能解决有没有，不能解决准不准、可不可改" | **被 2024-2026 进展部分推翻** | **需要更新** |

---

## 1. Posemy.art / MagicPoser：完全坐实"黑盒"

| 工具 | OBJ 含骨骼 | 含角度数值 | 可 Python Diff | 可批量 | 可离线 |
|---|---|---|---|---|---|
| **Posemy.art** | 否 | 否 | 否（只能 mesh diff） | 否 | 否（FAQ 强制联网） |
| **MagicPoser** | 否 | 否（OBJ）；`.mp` 未公开 | 否 | 否 | 未公开 |

- **骨骼模型 / 关节格式 / 坐标系**：两者**均未公开**
- **导出格式**：Posemy 只导 OBJ + 2D 图像；MagicPoser 多一个私有 `.mp`（仅 Master 订阅，schema 未公开）
- **结论**：定位是"艺术家摆姿势"，不是"工程化资产管理"。**满足工程目标的项目计数 = 0**

来源：[posemy.art/features](https://posemy.art/features/)、[posemy.art/faq](https://posemy.art/faq/)、[magicposer.com](https://magicposer.com/)、[magicposer.com/pricing-2.html](https://magicposer.com/pricing-2.html)

---

## 2. DWPose：时序不可用，单帧可用

- **基本**：IDEA-Research, ICCVW 2023, [arXiv:2307.09288](https://arxiv.org/abs/2307.09288)。133 关键点 = 17 body + 6 foot + 68 face + 21×2 hand。**逐帧独立推理，无时序约束**。论文未报 jitter 指标。
- **退化**：侧脸/俯仰关键点错位；多人重叠左右肢误绑；自遮挡（盘腿/抱臂）跨肢体错认；手部 21 点常丢 1-3 点 → SD 画手"六指"
- **时序 >5s**：任意帧抖动污染 ControlNet 时序一致性
- **绕过路径**：用 VideoPose3D / MotionBERT / MotionAGFormer 先做时序平滑，再渲染成图
- **GitHub 主仓**：[IDEA-Research/DWPose](https://github.com/IDEA-Research/DWPose)；ONNX 维护活跃，原生主线已定型
- **ComfyUI 封装**：[Fannovel16/comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux)
- **WebUI 封装**：旧 [patrickvonplaten/controlnet_aux](https://github.com/patrickvonplaten/controlnet_aux)（已迁移 HuggingFace）

---

## 3. 绕开识别的姿态数据源

| 格式 | 维度 | Git 友好 | 体积/帧 | 工具生态 | 一句话 |
|---|---|---|---|---|---|
| **SMPL** | pose 72 + shape 10 + trans 3 | ★★ | ~4KB | ★★★★★ | 参数化人体 SOTA，学术事实标准 |
| **SMPL-H** | + 手部 36 = ~141 维 | ★★ | ~6KB | ★★★★ | 含手 |
| **SMPL-X** | SMPL-H + jaw/eye/face = ~187 维 | ★★ | ~8KB | ★★★★ | expressive，含表情 |
| **VRM 1.0** | glb + JSON + humanBones（68 个规范骨骼名） | ★★★ | ~MB级 | ★★★★ | VTuber/Web3D 事实标准 |
| **VRMA** | 仅骨骼旋转，glTF扩展 | ★★★★ | <50KB | ★★★ | VRM Animation 专用 |
| **BVH** | 纯文本 HIERARCHY + MOTION | ★★★★★ | ~150 float/帧 | ★★★★★ | **最 Git 友好** |
| **glTF** | JSON + bin（LFS） | ★★★ | ~30KB+bin | ★★★★★ | KHR_animation_pointer 可走路径 |
| **FBX ASCII** | 明文但体积爆炸 | ★★★★ | 1-5MB/100帧 | ★★★★ | 100帧就能把仓库搞大 |
| **USD ASCII** | Pixar 标准，scene+animation | ★★★★★ | ~50KB | ★★★★ | Blender 4.2+ 内置导出 |

**Git 友好度排序**（按纯文本 diff）：BVH > USD ASCII > VRMA > glTF > FBX-ASCII > SMPL npz

**推荐组合**：**主存 BVH/VRMA/USD ASCII**（文本），**骨骼/网格用 glTF + LFS**。**绝对不要把 .blend 提交**。

---

## 4. AI 生图/生视频模型对姿态输入的支持矩阵

| 模型 | 接受 SMPL 数值? | 接受 DWPose npy? | 接受关键点图? | 推荐输入路径 |
|---|---|---|---|---|
| **ControlNet (SDXL/FLUX/SD3)** | ❌ | ❌ | ✅ | **离线骨架图渲染** |
| **AnimateDiff + SparseCtrl** | ❌ | ❌ | ✅（sparse） | 离线骨架图 |
| **AnimateAnyone / MagicAnimate** | ❌ | 半 | ✅（DensePose IUV） | DensePose 序列 |
| **MimicMotion**（腾讯+上交） | ❌ | ✅ | ✅ | **直接吃 npy，可 diff** |
| **StableAnimator**（复旦+MSRA） | ❌ | 内部 | ✅ | 参考视频驱动 |
| **Wan2.1/2.2-Animate**（阿里） | ❌ | 内部 | ✅ | 参考视频整体 |
| **HunyuanVideo-Avatar**（腾讯） | ❌ | ❌ | ❌ | **音频驱动，绕开姿态** |
| **CogVideoX / SVD / VideoCrafter / I2VGen-XL** | ❌ | ❌ | 部分 | 仍需 ControlNet 桥 |
| **DMV3D / GauHuman / GaussianAvatar** | ✅ SMPL-X | ❌ | ❌ | **原生数值** |
| **SMPLer-X / SiTH / HMP**（人体专用） | ✅ | ❌ | ❌ | **原生数值** |

**关键结论**：
- 2D 生图/生视频模型**几乎全部要"图"**（关键点图 / DensePose IUV）
- **MimicMotion** 是唯一 2D 视频模型直接吃 DWPose npy
- **3D 人体专用模型**（DMV3D / SMPLer-X）原生吃 SMPL 数值
- **HunyuanVideo-Avatar** 通过音频绕开姿态输入

这就是为什么 **"数值 → 离线渲染骨架图" 这道桥必须自建**。

---

## 5. 现成开源项目地图（按你的五大目标打分）

### 5.1 编辑器/创作

| 项目 | URL | 类型 | 输入 | 输出 | 评估 |
|---|---|---|---|---|---|
| **YuBan834/vrma-lab** | github.com/YuBan834/vrma-lab | Browser Web App + Agent SDK | VRM + FBX/VRMA | VRMA | **最对口**：浏览器优先、本地运行、AI agent SDK（`window.vrmaLab.inspect/edit/review/validate/export`） |
| **nanasi-apps/vrm-animation-web-editor** | github.com/nanasi-apps/vrm-animation-web-editor | Browser Web (Vue 3 + Vite) | VRM 1.0 + VRMA | VRMA | 时间线 / 关键帧 / 表情 / LookAt 都能改 |
| **Kanee18/VRMA-studio** | github.com/Kanee18/VRMA-studio | 桌面 (Tauri) | VRM + VRMA | VRMA | 剪/拼/对齐，类似视频剪辑工作流 |
| **GAOLIB** (GaoShanPictures) | github.com/GaoShanPictures/GAOLIB | Blender Add-on | Blender Armature Pose/Animation | JSON + GIF | **类 Maya Studio Library**，目录式仓库 |
| **huchenlei/sd-webui-openpose-editor** | github.com/huchenlei/sd-webui-openpose-editor | A1111 WebUI 扩展 | ControlNet preprocessor | OpenPose JSON/PNG | 单次创作单次回传，缺库 |
| **westNeighbor/ComfyUI-ultimate-openpose-editor** | github.com/westNeighbor/ComfyUI-ultimate-openpose-editor | ComfyUI 节点 | POSE_KEYPOINT / JSON | OpenPose PNG / JSON | 多人物、按部位缩放、JSON 透传 |
| **pururin777/ComfyUI-Manual-Openpose** | github.com/pururin777/ComfyUI-Manual-Openpose | ComfyUI 节点 | 图像批次 | 手工 OpenPose JSON | 唯一支持批处理手画 OpenPose |

### 5.2 转换/批入库

| 项目 | URL | 类型 | 功能 |
|---|---|---|---|
| **tk256ailab/fbx2vrma-converter** | github.com/tk256ailab/fbx2vrma-converter | CLI (Node.js) | **Mixamo FBX → VRMA 批量**，52-bone 含手指 |
| **saturday06/VRM-Addon-for-Blender** | github.com/saturday06/VRM-Addon-for-Blender | Blender Add-on | **VRM 1.0/0.x + VRMA 双向**，含 Python Scripting API |
| **BacteriaJun/BVH-Motion-Retargeter** | github.com/BacteriaJun/BVH-Motion-Retargeter | Blender Add-on | **BVH → VRM/Mixamo/UE5**，JSON 映射文件 |
| **vrm-mixamo-retargeter** (saori-eth) | github.com/saori-eth/vrm-mixamo-retargeter | JS 库 | Mixamo FBX → VRM Humanoid bone maps |
| **Renforce-Dynamics/blender_bvh2npz** | github.com/Renforce-Dynamics/blender_bvh2npz | Batch | BVH → 标准 SMPL-X npz |
| **Beat-in-our-hearts/Blender-SMPL-X-Animation-Exporter** | github.com/Beat-in-our-hearts/Blender-SMPL-X-Animation-Exporter | Blender Add-on | 标准 SMPL-X npz 导出 |
| **butaixianran/Blender-Vmd-Retargeting** | github.com/butaixianran/Blender-Vmd-Retargeting | Blender Add-on | MMD .vmd ↔ Blender/Daz |
| **daim1993/auto-bone-retarget-addon** | github.com/daim1993/auto-bone-retarget-addon | Blender Add-on | Mixamo/AccuRig/Rigify 互转 |
| **Axleonex/BoneForge** | github.com/Axleonex/BoneForge_ALTERNATIVE_CATS_for_5.0_Blender | Blender Add-on | VRM 0/1 + VMD + Mixamo 互转（CATS 复活版） |

### 5.3 库 / 运行时

| 项目 | URL | 类型 | 功能 |
|---|---|---|---|
| **pixiv/three-vrm** | github.com/pixiv/three-vrm | JS 库 | VRM 0.x/1.0 + three.js 加载渲染，**事实标准** |
| **pixiv/three-vrm-animation** | github.com/pixiv/three-vrm-animation | JS 库 | VRMA 播放 |
| **vchoutas/smplx** | github.com/vchoutas/smplx | Python 库 | SMPL-X 官方，`pip install smplx[all]` |
| **nghorbani/amass** | github.com/nghorbani/amass | 数据集 + loader | AMASS SMPL/H 加载器 |
| **Meshcapade/SMPL_blender_addon** | GitLab: tuebingen.mpg.de/jtesch/smplx_blender_addon | Blender Add-on | **SMPL/H/X/SUPR 加载 + Blender armature**（GitHub README 标"已废弃"） |
| **sandraschi/blender-mcp** | github.com/sandraschi/blender-mcp | MCP Server | 41 portmanteau 工具，headless 默认，VRM/FBX/USD 批处理 |

### 5.4 渲染骨架图（绕开识别）

| 项目 | URL | 类型 | 功能 |
|---|---|---|---|
| **rmarma/skeleton2dwposemap** | github.com/rmarma/skeleton2dwposemap | Blender Add-on | **Blender 骨架 → DWPose 风格图（无识别）** ← 直接对齐用户需求 |
| **MagosDigitalStudio/ComfyUI-Magos-Nodes** | github.com/MagosDigitalStudio/ComfyUI-Magos-Nodes | ComfyUI 节点 | "DWPose & NLF skeleton editor, retargeter, renderer" |

### 5.5 数据 / 动捕

| 项目 | URL | 类型 | 功能 |
|---|---|---|---|
| **AMASS** | amass.is.tue.mpg.de | 数据集 | **40+ 小时 SMPL+H 动作库**，注册下载 |
| **HumanML3D** | ericchen1903.github.io/HumanML3D | 数据集 | text-to-motion 事实基准 |
| **Motion-X** | — | 数据集 | AMASS + 文本 + 音频 + 物体交互 |
| **BABEL** | — | 数据集 | 动作语义标注 |
| **lerobot/SMPL_samples** | huggingface.co/datasets/lerobot/SMPL_samples | HF 数据集 | 13 个 SMPL 样本（walk/jump/dance） |
| **HuggingFace 456 个 pose Space** | hf.co/spaces (search: pose) | HF Spaces | 大量 Gradio demo |

### 5.6 AI 流水线端到端

| 项目 | URL | 类型 | 功能 |
|---|---|---|---|
| **MimicMotion** (Tencent) | github.com/tencent/MimicMotion | 视频扩散 | **直接吃 pose npy**，可 diff |
| **Wan-Video/Wan2.2** | github.com/Wan-Video/Wan2.2 | T2V/I2V/V2V | MoE 视频生成 + Animate 角色替换 |
| **Tencent-Hunyuan/HunyuanVideo** | github.com/Tencent-Hunyuan/HunyuanVideo | T2V | HunyuanVideo-Avatar 音频驱动 |
| **TencentARC/MotionCtrl** | github.com/TencentARC/MotionCtrl | 视频扩散 | 相机+物体运动解耦，**轨迹数值输入** |
| **VAST-AI-Research/UniRig** | github.com/VAST-AI-Research/UniRig | 自动骨架 | **任意 mesh → SMPL-like 骨架**（SIGGRAPH 2025） |
| **mikehalleen/the-halleen-machine** | github.com/mikehalleen/the-halleen-machine | video 流水线 | **"姿态资产库"概念 + ComfyUI + Agent skill** |
| **squall01337/mixamo-llm-mocap** | github.com/squall01337/mixamo-llm-mocap | end-to-end | GVHMR(SMPL-X) → Mixamo + spec-driven retarget + QA 门 |
| **lewdineer/Kimodo_Blender_Bridge** | github.com/lewdineer/Kimodo_Blender_Bridge | Blender Add-on | 文本 → Kimodo → BVH → Blender |

### 5.7 Awesome 索引（非项目但作为扩展）

- [curemagiclab-jp/awesome-vrm](https://github.com/curemagiclab-jp/awesome-vrm) — VRM 生态最全索引
- [modenaxe/awesome-biomechanics](https://github.com/modenaxe/awesome-biomechanics) — 动捕+生物力学
- [animate-x/Awesome-human-motion](https://github.com/animate-x/Awesome-human-motion) — 动捕+生成+具身智能
- [pansanity666/Awesome-Avatars](https://github.com/pansanity666/Awesome-Avatars) — avatar 生成/编辑
- [fangjw-0722/Awesome-Wearable-Motion-Capture](https://github.com/fangjw-0722/Awesome-Wearable-Motion-Capture) — 可穿戴动捕

---

## 6. 自建 ROI 最高的空白（按优先级）

| # | 空白 | 必要性 | 估时 | 估代码量 |
|---|---|---|---|---|
| 1 | **VRMA → DWPose 风格骨架 PNG 离线渲染器**（无识别） | 必须 | 1 周 | ~300 行 |
| 2 | **ComfyUI "OpenPose 姿态预设库"节点**（tag/搜索/batch-apply） | 必须 | 1 周 | ~400 行 |
| 3 | **姿态 Semantic Diff CLI**（"左脚抬高 5°"而非浮点 diff） | 必须 | 3 天 | ~150 行 |
| 4 | **SMPL-X → VRM 带语义 retarget**（手/表情映射表） | 强烈建议 | 2 周 | ~800 行 |
| 5 | **"姿态 pack" schema 标准**（.pose.json + .vrma + .preview.png + .meta.yaml） | 自建规范 | 2 天 | spec 文档 |
| 6 | **VRoid Pose 格式 ↔ OpenPose 关键点转换 CLI** | 自建桥 | 2 天 | ~100 行 |
| 7 | **批量姿态质量评估**（脚滑/穿模/关节超限） | 高难度 | 1 月 | ~500 行 |

---

## 7. 推荐路线

### 路线 A：VRMA 优先（Web / 角色驱动场景）
```
编辑：nanasi-apps/vrm-animation-web-editor 或 YuBan834/vrma-lab（任选一 fork）
入库：tk256ailab/fbx2vrma-converter（Mixamo FBX 批量转 VRMA）
Blender 桥：saturday06/VRM-Addon-for-Blender
骨架渲染：rmarma/skeleton2dwposemap fork + 自写 VRMA 适配
Git 资产：.vrma + .meta.yaml + preview.png 三件套
视频生成：Wan2.2-Animate（参考视频驱动）或 HunyuanVideo-Avatar（音频驱动）
```

### 路线 B：Blender 平衡（艺术家参与）
```
Pose 库：GAOLIB
导出：saturday06/VRM-Addon-for-Blender（VRMA）+ BVH/FBX-ascii/glTF/USD ASCII
Headless：sandraschi/blender-mcp（41 工具，headless 默认）
骨架渲染：rmarma/skeleton2dwposemap 或自写 OpenPose/DWPose 渲染插件
视频生成：MimicMotion（吃 pose npy，可 diff）或 Wan2.2-Animate
```

### 路线 C：SMPL-X 学术（科研 / 大批量 / text-to-motion）
```
库：vchoutas/smplx
数据：AMASS（注册下载，40+ 小时）
Blender：Meshcapade/SMPL_blender_addon（GitLab 新家）
导出：Beat-in-our-hearts/Blender-SMPL-X-Animation-Exporter
跨骨架：UniRig（任意 mesh → SMPL-like 骨架）
生视频：MimicMotion / MotionCtrl（数值输入）
可视化 review：rerun.io
```

---

## 8. 风险与坑

1. **SMPL-X 协议**：`.pkl` 不可商用，必须联系 `ps-licensing@tue.mpg.de`；AMASS 仅注册可用
2. **VRM 模型许可**：多数禁止商用，必须读 `meta.licenseName` / `commercialUssage`
3. **FBX 版本**：Autodesk 不保证 binary/ASCII roundtrip；推荐只导出 BVH/VRMA/USD ASCII
4. **BVH 兼容性**：不同 mocap 工具 channel 顺序不同（Blender `[tx,ty,tz,rx,ry,rz]` vs Maya 可能不同）
5. **Git LFS 成本**：100 帧 fbx~5MB × 100 动作 = 500MB，GitHub 免费 1GB 配额几次就爆；考虑 git-annex/S3
6. **Meshcapade SMPL add-on 已废弃**：README 明示，新家在 GitLab
7. **blender-mcp 首次启动 5-10s**：高频调用要 keep-alive bridge
8. **pixiv/three-vrm 默认 dev 分支**：固定 release tag，避免 npm 2.x 与 spec 不同步

---

## 9. 关键反转：动作迁移 vs 原判断

用户原判断："动作迁移只能解决有没有，不能解决准不准、可不可改"
**在 2024-2026 年部分被推翻**：

| 反证项目 | 反驳哪个子判断 | 证据 |
|---|---|---|
| MimicMotion | "可不可改" | 直接吃 DWPose npy 数值，npy 改完即生效 |
| MotionCtrl / CameraCtrl / DragAnything | "可不可改" | 相机/物体轨迹是浮点数数组输入 |
| MDM / MotionGPT / UniRig | "可不可改" | 输出参数化 SMPL 关节，可 diff |
| Wan2.1/2.2-Animate | "可不可改" | 内部直接处理骨骼信号，绕过"必须先渲成图" |
| HunyuanVideo-Avatar | "可不可改" | 完全用音频绕开姿态输入 |

**但"准不准"依然成立**：同输入不同 seed 输出质量浮动 30%；物理合理性（脚滑/穿模/漂浮）依然薄弱。

---

## 10. 引用来源（agent 报告采样的 URL）

### Posemy / MagicPoser
- https://posemy.art/
- https://posemy.art/features/
- https://posemy.art/faq/
- https://posemy.art/pricing/
- https://posemy.art/sitemap.xml
- https://magicposer.com/
- https://magicposer.com/pricing-2.html

### DWPose / 识别
- https://arxiv.org/abs/2307.09288
- https://github.com/IDEA-Research/DWPose
- https://github.com/Fannovel16/comfyui_controlnet_aux

### SMPL / 数据集
- https://github.com/vchoutas/smplx
- https://amass.is.tue.mpg.de
- https://ericchen1903.github.io/HumanML3D

### VRM / VRMA 生态
- https://github.com/pixiv/three-vrm
- https://github.com/pixiv/three-vrm-animation
- https://github.com/saturday06/VRM-Addon-for-Blender
- https://github.com/YuBan834/vrma-lab
- https://github.com/nanasi-apps/vrm-animation-web-editor
- https://github.com/Kanee18/VRMA-studio
- https://github.com/tk256ailab/fbx2vrma-converter
- https://github.com/saori-eth/vrm-mixamo-retargeter
- https://github.com/curemagiclab-jp/awesome-vrm

### Blender 工具
- https://github.com/GaoShanPictures/GAOLIB
- https://github.com/BacteriaJun/BVH-Motion-Retargeter
- https://github.com/sandraschi/blender-mcp
- https://github.com/rmarma/skeleton2dwposemap
- https://gitlab.tuebingen.mpg.de/jtesch/smplx_blender_addon
- https://github.com/Beat-in-our-hearts/Blender-SMPL-X-Animation-Exporter
- https://github.com/butaixianran/Blender-Vmd-Retargeting
- https://github.com/daim1993/auto-bone-retarget-addon
- https://github.com/Axleonex/BoneForge_ALTERNATIVE_CATS_for_5.0_Blender

### ComfyUI / WebUI
- https://github.com/huchenlei/sd-webui-openpose-editor
- https://github.com/huchenlei/ComfyUI-openpose-editor
- https://github.com/westNeighbor/ComfyUI-ultimate-openpose-editor
- https://github.com/pururin777/ComfyUI-Manual-Openpose
- https://github.com/space-nuko/ComfyUI-OpenPose-Editor
- https://github.com/MagosDigitalStudio/ComfyUI-Magos-Nodes

### AI 生视频 / 动作迁移
- https://github.com/tencent/MimicMotion
- https://github.com/Wan-Video/Wan2.2
- https://github.com/Tencent-Hunyuan/HunyuanVideo
- https://github.com/TencentARC/MotionCtrl
- https://github.com/VAST-AI-Research/UniRig
- https://github.com/mikehalleen/the-halleen-machine
- https://github.com/squall01337/mixamo-llm-mocap
- https://github.com/lewdineer/Kimodo_Blender_Bridge
- https://github.com/GuyTevet/motion-diffusion-model

---

## 11. 下一步决策建议

如果你今天就要动起来：

1. **路径 A（最快可跑通）**：fork [nanasi-apps/vrm-animation-web-editor](https://github.com/nanasi-apps/vrm-animation-web-editor) + 装 [saturday06/VRM-Addon-for-Blender](https://github.com/saturday06/VRM-Addon-for-Blender)，用 [tk256ailab/fbx2vrma-converter](https://github.com/tk256ailab/fbx2vrma-converter) 把 Mixamo 2000+ 动作批量入库

2. **路径 B（最稳）**：装 Blender 4.2 LTS + [GAOLIB](https://github.com/GaoShanPictures/GAOLIB)，用 [sandraschi/blender-mcp](https://github.com/sandraschi/blender-mcp) headless 跑批导出 BVH/USD ASCII

3. **路径 C（最高上限）**：[Meshcapade](https://gitlab.tuebingen.mpg.de/jtesch/smplx_blender_addon) + [AMASS](https://amass.is.tue.mpg.de) + 自写"姿态 → 离线骨架图"渲染器（[rmarma/skeleton2dwposemap](https://github.com/rmarma/skeleton2dwposemap) 方向对路）

三个路径**不互斥**：通常先 B（最稳）打地基，再 A（VRMA 友好）做分发，再 C（SMPL-X）做学术扩展。
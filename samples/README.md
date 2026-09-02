# 样例说明：一个人在低头看手机

**文件**：[looking-down-phone.json](/E:/Program/JavaGuide/Codes/zzdzz-pose-tool/samples/looking-down-phone.json)

## 这是什么

单帧静态姿态数据，**DWPose/OpenPose 133-keypoint JSON 格式**（含 body 17 + face 6 + hand L 9 + hand R 9 + foot 6，简化版演示用）。

## 关键设计要点

| 部位 | 坐标特征 | 表达的姿态含义 |
|---|---|---|
| `nose` (256, 180) | 位于脸部正中偏低 | 头部前倾约 30° |
| `left/right_eye` (y=175) | y < nose.y | 双眼视线朝下 |
| `left/right_shoulder` (y=235) | 微抬 | 持手机时肩膀轻微耸起 |
| `left_wrist` (248, 340) / `right_wrist` (268, 345) | x 差距仅 20px | 双手在身前合拢 |
| `right_hand_index_tip` (263, 350) | 食指伸出 + 其他手指弯曲 | 右手点击屏幕 |
| `left/right_hip` (y=360) | 水平、居中 | 躯干直立 |

## 测试用法

### 1. 测试 ControlNet 兼容性
把 JSON 转成 OpenPose 骨架图 PNG（用 `controlnet_aux` 或 ComfyUI 节点），喂给 SDXL/FLUX/Wan2.x：
```bash
# 用 controlnet_aux 渲染
python -c "
from controlnet_aux import OpenposeDetector
import json
import numpy as np

with open('looking-down-phone.json') as f:
    data = json.load(f)

# 提取 body 17 关键点
keypoints = [(kp['x'], kp['y'], kp['confidence']) for kp in data['people'][0]['pose_keypoints_2d']]
arr = np.array(keypoints).flatten()  # [x1,y1,c1,x2,y2,c2,...]

detector = OpenposeDetector.from_pretrained('lllyasviel/Annotators')
# 喂给检测器反向验证
img = detector(arr.reshape(1, -1))
img.save('looking-down-phone.png')
"
```

### 2. 测试 Git Diff（最重要的测试！）
复制一份改成"抬头看天"：
```bash
cp looking-down-phone.json looking-up-sky.json
# 编辑 looking-up-sky.json：把 nose.y 从 180 改成 130（抬头），eye.y 从 175 改成 125
git diff looking-down-phone.json looking-up-sky.json
```

**预期 diff 输出**：
```diff
-        {"id": 0, "name": "nose", "x": 256, "y": 180, "confidence": 0.95},
+        {"id": 0, "name": "nose", "x": 256, "y": 130, "confidence": 0.95},
-        {"id": 1, "name": "left_eye", "x": 248, "y": 175, "confidence": 0.93},
+        {"id": 1, "name": "left_eye", "x": 248, "y": 125, "confidence": 0.93},
```
**能精确指出"鼻子 y 偏移 +50，眼 y 偏移 +50"**，这就是"可版本管理"的核心。

### 3. 测试 DWPose 反向校验
用 DWPose 检测这份 JSON 渲染出来的骨架图，看检测出的关键点和原始坐标是否一致：
```python
# 如果误差 < 5px，说明这份"理论姿态数据"可以在不经过图像识别的情况下被 AI 使用
# 如果误差 > 20px，说明需要把这套坐标系映射到 DWPose 的训练坐标系
```

### 4. 测试批量处理
把 100 个类似的 JSON 放在 `samples/batch/` 目录下，写一个脚本批量渲染：
```bash
python batch_render.py samples/batch/ output/
```

## 下一步

如果你测试通过（ControlNet 能正确识别、git diff 精确、DWPose 反向误差小），就可以：
1. 进入正式管线搭建
2. 把这个 JSON 格式封装成 `pose pack`（.pose.json + preview.png + meta.yaml）
3. 自建"VRMA → DWPose 风格骨架 PNG 离线渲染器"（fork rmarma/skeleton2dwposemap）

如果测试发现坐标系不匹配或 ControlNet 识别失败，我们再调整坐标轴约定或格式。
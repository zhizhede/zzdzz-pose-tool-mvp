"""动作图片 → 人体关键点 → COCO-18 pose 数据（DWPose ONNX 本地推理）。

链路：YOLOX 检测人 → DWPose 输出 COCO-WholeBody 133 点 → 取身体 17 点
合成 OpenPose COCO-18（颈部=双肩中点）。纯 onnxruntime CPU 推理，
无需 mmpose 全家桶。

模型文件（ONNX）默认目录 E:/Program/zzdzz-ai/models/dwpose/：
  yolox_l.onnx          人体检测
  dw-ll_ucoco_384.onnx  全身姿态（SimCC 输出）

精度边界：单张图片只能得到 2D 关键点（亚像素级精确），无 3D 深度——
产出的 pose.json 不含 pose_keypoints_3d（不能导 BVH/深度图），朝向未知。
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

DEFAULT_MODEL_DIR = Path(os.environ.get(
    "DWPOSE_MODEL_DIR", "E:/Program/zzdzz-ai/models/dwpose"))

# COCO-17（COCO-WholeBody 前 17 点）→ OpenPose COCO-18 的下标映射。
# None 表示合成点（颈部 = 双肩中点）。
C17_TO_18 = [
    0,        # 0 nose
    None,     # 1 neck（合成）
    6, 8, 10, # 2 r_sho 3 r_el 4 r_wri（COCO 的"right_*"=人物自身右侧）
    5, 7, 9,  # 5 l_sho 6 l_el 7 l_wri
    12, 14, 16,  # 8 r_hip 9 r_knee 10 r_ank
    11, 13, 15,  # 11 l_hip 12 l_knee 13 l_ank
    2, 1,     # 14 r_eye 15 l_eye
    4, 3,     # 16 r_ear 17 l_ear
]
SHOULDER_PAIR = (5, 6)  # 合成颈部的双肩下标


class DWPoseDetector:
    def __init__(self, model_dir: str | Path | None = None):
        import onnxruntime as ort

        model_dir = Path(model_dir or DEFAULT_MODEL_DIR)
        yolo_path = model_dir / "yolox_l.onnx"
        pose_path = model_dir / "dw-ll_ucoco_384.onnx"
        if not pose_path.exists():
            raise FileNotFoundError(
                f"缺少模型 {pose_path}（下载见 docs/generation-manual.md 的模型清单）")
        so = ort.SessionOptions()
        so.log_severity_level = 3
        # 人体检测器可选：官方 yzd-v 的 yolox_l.onnx 上传损坏（截断），
        # 缺失时退化为整图推理（单人居中图片效果良好，多人图暂不支持）
        self.det = None
        if yolo_path.exists():
            try:
                self.det = ort.InferenceSession(str(yolo_path), so,
                                                providers=["CPUExecutionProvider"])
            except Exception:
                self.det = None
        self.pose = ort.InferenceSession(str(pose_path), so, providers=["CPUExecutionProvider"])

    # ---- YOLOX 人体检测（可选） ----
    def _detect_person(self, image_bgr: np.ndarray) -> tuple[float, float, float, float]:
        """返回画面中置信度最高的人 bbox (x0, y0, x1, y1)，原图坐标。"""
        if self.det is None:
            h, w = image_bgr.shape[:2]
            return (0.0, 0.0, float(w), float(h))  # 整图回退
        h, w = image_bgr.shape[:2]
        size = 640
        padded, ratio = _letterbox(image_bgr, (size, size))
        x = padded.astype(np.float32) / 255.0
        x = np.ascontiguousarray(x[:, :, ::-1].transpose(2, 0, 1)[None])  # BGR→RGB, HWC→BCHW
        name = self.det.get_inputs()[0].name
        out = self.det.run(None, {name: x})[0]  # [1, N, 85] 或 [1, N, 6]
        pred = np.squeeze(out, axis=0)

        # 兼容两种导出：带 obj+80 类（85）或已合成单分数（6 列）
        if pred.shape[-1] >= 85:
            scores = pred[:, 4:5] * pred[:, 5:]
            class_ids = scores.argmax(axis=1)
            conf = scores.max(axis=1)
            person_mask = class_ids == 0
        else:
            conf = pred[:, 4]
            person_mask = np.ones(len(pred), dtype=bool)
        boxes = pred[:, :4] / ratio  # 反 letterbox

        best, best_conf = None, 0.0
        for (x0, y0, x1, y1), c, keep in zip(boxes, conf, person_mask):
            if not keep or c < 0.5:
                continue
            if c > best_conf:
                best_conf = c
                best = (max(x0, 0), max(y0, 0), min(x1, w), min(y1, h))
        if best is None:
            raise ValueError("图中未检测到人物（yolox 置信度 < 0.5）")
        return best

    # ---- DWPose 姿态 ----
    def _infer_pose(self, image_bgr: np.ndarray, bbox) -> np.ndarray:
        """返回 133×3 关键点（原图坐标 x, y, 置信度）。"""
        h, w = image_bgr.shape[:2]
        x0, y0, x1, y1 = [int(v) for v in bbox]
        w1, h1 = x1 - x0, y1 - y0
        # 保持宽高比 pad 到 288:384（W:H）
        aspect = 288 / 384
        if w1 / h1 < aspect:
            pad_w = int(h1 * aspect - w1)
            crop = cv2.copyMakeBorder(image_bgr[y0:y1, x0:x1], 0, 0,
                                      pad_w // 2, pad_w - pad_w // 2,
                                      cv2.BORDER_CONSTANT)
        else:
            pad_h = int(w1 / aspect - h1)
            crop = cv2.copyMakeBorder(image_bgr[y0:y1, x0:x1], 0, pad_h - pad_h // 2,
                                      0, 0, cv2.BORDER_CONSTANT)
        inp = cv2.resize(crop, (288, 384), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
        inp = (inp - np.array([0.485, 0.456, 0.406], dtype=np.float32)) \
            / np.array([0.229, 0.224, 0.225], dtype=np.float32)
        inp = np.ascontiguousarray(inp[:, :, ::-1].transpose(2, 0, 1)[None])  # BGR→RGB, HWC→BCHW
        name = self.pose.get_inputs()[0].name
        outputs = self.pose.run(None, {name: inp})

        # SimCC 输出：[1, 133, W/2] 与 [1, 133, H/2]；argmax 后缩回
        if len(outputs) == 2:
            sx, sy = outputs
            xs = np.argmax(sx[0], axis=1)
            ys = np.argmax(sy[0], axis=1)
            vals = np.maximum(sx[0].max(axis=1), sy[0].max(axis=1))
            scale_x = crop.shape[1] / sx.shape[2]
            scale_y = crop.shape[0] / sy.shape[2]
            xs = xs * scale_x / 2
            ys = ys * scale_y / 2
        else:  # 热图输出 [1, 133, H', W']
            heat = outputs[0][0]
            ys, xs = heat.reshape(heat.shape[0], -1).argmax(axis=1)
            vals = heat.reshape(heat.shape[0], -1).max(axis=1)
            scale_x = crop.shape[1] / heat.shape[2]
            scale_y = crop.shape[0] / heat.shape[1]
            xs = xs * scale_x
            ys = ys * scale_y

        kps = np.zeros((133, 3), dtype=np.float32)
        kps[:, 0] = xs + x0
        kps[:, 1] = ys + y0
        kps[:, 2] = vals
        return kps

    def __call__(self, image_path: str | Path) -> np.ndarray:
        """图片路径 → 18×[x, y, score]（OpenPose COCO-18，像素坐标）。"""
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"无法读取图片：{image_path}")
        bbox = self._detect_person(image)
        kps133 = self._infer_pose(image, bbox)

        out = []
        for target in C17_TO_18:
            if target is None:  # 颈 = 双肩中点
                a, b = kps133[SHOULDER_PAIR[0]], kps133[SHOULDER_PAIR[1]]
                conf = min(a[2], b[2]) if a[2] > 0.3 and b[2] > 0.3 else 0.0
                out.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, float(conf)))
            else:
                k = kps133[target]
                out.append((float(k[0]), float(k[1]), float(min(1.0, k[2] / 1.5))))
        return np.array(out, dtype=np.float32)


def _letterbox(image: np.ndarray, size: tuple[int, int]):
    """等比缩放 + 填充到目标尺寸，返回 (图, 缩放比)。"""
    h, w = image.shape[:2]
    ratio = min(size[0] / w, size[1] / h)
    resized = cv2.resize(image, (int(w * ratio), int(h * ratio)))
    ph, pw = size[1] - resized.shape[0], size[0] - resized.shape[1]
    top, left = ph // 2, pw // 2
    out = cv2.copyMakeBorder(resized, top, ph - top, left, pw - left,
                             cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return out, ratio


def detect_to_pose_dict(image_path: str | Path,
                        model_dir: str | Path | None = None) -> dict:
    """图片 → pose.json 兼容 dict（2D 资产：无 3D/朝向）。"""
    detector = DWPoseDetector(model_dir)
    kps = detector(str(image_path))
    flat = []
    for x, y, c in kps:
        flat.extend([round(float(x), 1), round(float(y), 1), round(float(min(max(c, 0.0), 1.0)), 2)])
    return {
        "version": "0.2",
        "meta": {"source_format": "dwpose-image"},
        "people": [{"pose_keypoints_2d": flat}],
    }

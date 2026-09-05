"""safetensors 权重完整性扫描：逐张量统计 NaN/Inf。

背景：ModelScope/HF 镜像上出现过"头部合法、大小对、权重里散布 NaN"的坏副本
（如 CLIP-ViT-H image_encoder 的 layer13/18），下载后必须先扫描再入库。

用法:
    python tools/comfyui/scan_safetensors.py <文件.safetensors> [文件2 ...]

退出码: 0 = 干净；1 = 含 NaN/Inf 或读取失败。
"""

from __future__ import annotations

import json
import struct
import sys

import numpy as np

DTMAP = {"I64": "<i8", "I32": "<i4", "I16": "<i2", "F64": "<f8", "F32": "<f4", "F16": "<f2"}


def scan(path: str) -> bool:
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(n))
        base = 8 + n
        bad: list[tuple[str, int, int]] = []
        checked = 0
        for name, info in header.items():
            if name == "__metadata__":
                continue
            dt = DTMAP.get(info["dtype"])
            if dt is None:  # BF16 等 numpy 不直接支持，跳过数值检查
                continue
            count = 1
            for s in info["shape"]:
                count *= s
            f.seek(base + info["data_offsets"][0])
            arr = np.fromfile(f, dtype=np.dtype(dt), count=count)
            checked += 1
            nan_n = int(np.isnan(arr).sum())
            inf_n = int(np.isinf(arr).sum())
            if nan_n or inf_n:
                bad.append((name, info["dtype"], nan_n + inf_n))
        status = "✅ 干净" if not bad else f"❌ {len(bad)} 个张量含 NaN/Inf"
        print(f"{path}: {checked} 张量已扫 {status}")
        for name, dt, cnt in bad[:10]:
            print(f"   {name} ({dt}) 异常元素 {cnt}")
        return not bad


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    ok = True
    for p in sys.argv[1:]:
        ok = scan(p) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

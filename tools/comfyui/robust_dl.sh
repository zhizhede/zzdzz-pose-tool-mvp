#!/bin/bash
# 安全分段下载：手动续传循环，杜绝重复追加
# 用法: robust_dl.sh <URL> <总字节> <并行段数> <输出目录> <输出前缀>
set -u
URL="$1"; TOTAL="$2"; N="$3"; OUTDIR="$4"; PREFIX="$5"
mkdir -p "$OUTDIR"
CHUNK=$((TOTAL / N + 1))

dl_part() {
  local i="$1"
  local START=$((i * CHUNK))
  local END=$((START + CHUNK - 1))
  if [ "$END" -ge "$TOTAL" ]; then END=$((TOTAL - 1)); fi
  local WANT=$((END - START + 1))
  if [ "$WANT" -le 0 ]; then echo "[p$i] 非法 range"; return 1; fi
  local TMP="$OUTDIR/${PREFIX}_p${i}.tmp"
  local ATTEMPT=0
  while [ "$ATTEMPT" -lt 400 ]; do
    ATTEMPT=$((ATTEMPT + 1))
    local HAVE=0
    if [ -f "$TMP" ]; then HAVE=$(stat -c %s "$TMP"); fi
    if [ "$HAVE" -eq "$WANT" ]; then
      mv -f "$TMP" "$OUTDIR/${PREFIX}_p${i}"
      echo "[p$i] 完成 ($WANT 字节, $ATTEMPT 次尝试)"
      return 0
    fi
    if [ "$HAVE" -gt "$WANT" ]; then rm -f "$TMP"; HAVE=0; fi
    # 单次尝试，无 curl 自动重试；失败/停滞由本循环按实际偏移续传
    curl -fL --ssl-no-revoke --connect-timeout 15 --speed-limit 20000 --speed-time 20 \
      -s -r $((START + HAVE))-${END} -o - "$URL" >> "$TMP" 2>/dev/null
  done
  echo "[p$i] 失败: 400 次尝试未完成"
  return 1
}

PIDS=()
for i in $(seq 0 $((N-1))); do
  dl_part "$i" &
  PIDS+=($!)
done
FAIL=0
for p in "${PIDS[@]}"; do
  wait "$p" || FAIL=1
done
SUM=0
for i in $(seq 0 $((N-1))); do
  SZ=$(stat -c %s "$OUTDIR/${PREFIX}_p${i}" 2>/dev/null || echo 0)
  SUM=$((SUM + SZ))
done
if [ "$FAIL" -eq 0 ] && [ "$SUM" -eq "$TOTAL" ]; then
  echo "合计: $SUM / $TOTAL ✅ 全部完成"
  exit 0
else
  echo "合计: $SUM / $TOTAL ❌ 有失败"
  exit 1
fi

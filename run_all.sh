#!/usr/bin/env bash
# 一键复现：解 deck → 读图 → 自检 → 解析十月表 → 合并对照表
set -euo pipefail
cd "$(dirname "$0")"
DECK_DIR="${DECK_DIR:-../20261123}"

python scripts/extract_deck.py "$DECK_DIR/闪烁分析样本.pptx" data/sample
python scripts/extract_deck.py "$DECK_DIR/利用ISS来限制源尺度的理论以及初步样本.pptx" data/theory

if [ -n "${ZHIPU_API_KEY:-}" ]; then
  python scripts/read_fits.py "${WORKERS:-4}"
else
  echo "[skip] 未设置 ZHIPU_API_KEY，跳过读图（沿用已有 data/fits_readings.json）" >&2
fi

python scripts/iss.py --test
python scripts/make_bursts.py
python scripts/parse_october.py
python scripts/audit_october.py
python scripts/compare.py

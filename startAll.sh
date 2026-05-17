#!/usr/bin/env bash
# startAll.sh — KorASR 一键启动（前端 build + 后端 HTTPS）
#
# 用法：
#   ./startAll.sh             完整启动（build 前端 + 起后端）
#   ./startAll.sh --no-build  跳过 build（前端没改时省时间）
#
# 退出脚本：Ctrl+C
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJ_DIR"

# Conda env 里的 Python — 换机器/换路径时改这一行，或外部 export KORASR_PY=/path/to/python
KORASR_PY="${KORASR_PY:-/Users/rouro_599/miniconda3/envs/korasr/bin/python}"
if [ ! -x "$KORASR_PY" ]; then
  echo "[startAll] ERROR: Python 不存在: $KORASR_PY"
  echo "  改脚本顶部的 KORASR_PY 默认值，或外部 export KORASR_PY=/your/path"
  exit 1
fi

# 1) 释放 8000 端口
PID=$(lsof -nP -iTCP:8000 -sTCP:LISTEN -t 2>/dev/null || true)
if [ -n "$PID" ]; then
  echo "[startAll] 8000 端口已被 PID=$PID 占用，先关..."
  kill -TERM "$PID" 2>/dev/null || true
  sleep 1
  if kill -0 "$PID" 2>/dev/null; then
    kill -9 "$PID" 2>/dev/null || true
  fi
fi

# 2) 前端 build
if [ "${1:-}" != "--no-build" ]; then
  echo "[startAll] 构建前端..."
  npm --prefix "$PROJ_DIR/frontend" run build
fi

# 3) 起后端（前台运行，Ctrl+C 退出）
echo
echo "[startAll] 启动后端（HTTPS :8000）..."
echo "  打开 https://localhost:8000  （首次浏览器自签证书警告 → Advanced → Proceed）"
echo
exec env PYTHONUNBUFFERED=1 "$KORASR_PY" "$PROJ_DIR/start.py"

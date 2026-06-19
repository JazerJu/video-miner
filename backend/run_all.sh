#!/usr/bin/env bash
set -euo pipefail

# 虚拟环境检测：如果未激活且存在 venv，则自动激活
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  if [[ -f "./venv/bin/activate" ]]; then
    echo "Activating virtual environment..."
    source ./venv/bin/activate
  else
    echo "ERROR: Virtual environment not found at ./venv"
    echo "Hint: python -m venv venv  &&  source venv/bin/activate  &&  pip install -r requirements.txt"
    exit 1
  fi
fi

mkdir -p ./logs

export PORT="${PORT:-8080}"
export ENABLE_MCP="${ENABLE_MCP:-0}"
export MCP_PORT="${MCP_PORT:-8787}"
export VIDGO_URL="${VIDGO_URL:-}"

# 你的项目用的是 vid_go.settings -> 对应的 WSGI 入口如下
APP_MODULE="vid_go.wsgi:application"
LOG="./logs/gunicorn_$(date +%Y%m%d_%H%M%S).log"

export HTTP_PROXY="${HTTP_PROXY:-http://127.0.0.1:7890}"
export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7890}"
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1}"

echo "Using $(python -V) at $(which python)"

# 如被占用则报错并给出提示
if lsof -t -i tcp:"$PORT" >/dev/null 2>&1; then
  echo "ERROR: Port $PORT in use by PID(s): $(lsof -t -i tcp:$PORT | xargs)"
  echo "Hint: fuser -k ${PORT}/tcp   或   pkill -f 'manage.py runserver.*${PORT}'"
  exit 1
fi

if [[ "$ENABLE_MCP" == "1" ]]; then
  if lsof -t -i tcp:"$MCP_PORT" >/dev/null 2>&1; then
    echo "ERROR: MCP port $MCP_PORT in use by PID(s): $(lsof -t -i tcp:$MCP_PORT | xargs)"
    exit 1
  fi

  MCP_LOG="./logs/mcp_$(date +%Y%m%d_%H%M%S).log"
  nohup python -m uvicorn vid_go.mcp_asgi:application \
    --host "0.0.0.0" \
    --port "$MCP_PORT" \
    >> "$MCP_LOG" 2>&1 & MCP_PID=$!

  echo "MCP PID=$MCP_PID"
  echo "MCP Local:   http://localhost:${MCP_PORT}/mcp"
  hostname -I | xargs -n1 -I{} echo "MCP Network: http://{}:${MCP_PORT}/mcp"
  echo "MCP Log:     $(pwd)/$MCP_LOG"
fi

# 单进程多线程模式：
# - 解决 download_status 跨进程共享问题（无需 Redis）
# - I/O 密集型任务（下载、FFmpeg）不受 GIL 影响
# - 内存占用更低
# - 线程池提供并发能力（apps.py 中配置）
nohup python -m gunicorn "$APP_MODULE" \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --threads "$(( 2*$(nproc) + 1 ))" \
  --worker-class gthread \
  --timeout 300 \
  --access-logfile - --log-level info \
  >> "$LOG" 2>&1 & PID=$!

echo "PID=$PID"
echo "Local:   http://localhost:${PORT}/"
hostname -I | xargs -n1 -I{} echo "Network: http://{}:${PORT}/"
echo "Log:     $(pwd)/$LOG"
if [[ -n "$VIDGO_URL" ]]; then
  echo "VIDGO_URL=$VIDGO_URL"
fi

# 想现场看日志就保留这行；不想阻塞就注释掉
# tail -n 50 -f "$LOG"

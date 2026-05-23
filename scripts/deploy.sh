#!/usr/bin/env bash
# 一键启动 AlphaForge 决策驾驶舱 + 可选 ngrok 公网隧道。
# 用法：
#   bash scripts/deploy.sh              # 本地启动
#   bash scripts/deploy.sh --tunnel     # 本地 + ngrok 公网链接（需先 brew install ngrok）

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 1. 检查 venv
if [[ ! -x ".venv/bin/streamlit" ]]; then
  echo "✗ .venv 不存在或 streamlit 未安装"
  echo "  请先执行：python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# 2. 检查 .env
if [[ ! -f ".env" ]]; then
  echo "⚠️  .env 不存在 —— 复制 .env.example 后填入 GMI_API_KEY 才能调真 LLM"
  echo "    cp .env.example .env"
fi

# 3. 杀掉旧进程
pkill -f "streamlit run app/dashboard" 2>/dev/null || true
sleep 1

# 4. 启动 Streamlit
echo "🚀 启动 Streamlit on http://127.0.0.1:8501 ..."
nohup .venv/bin/streamlit run app/dashboard.py \
  --server.port 8501 --server.address 127.0.0.1 \
  > /tmp/alphaforge-streamlit.log 2>&1 &
STREAMLIT_PID=$!
echo "   PID: $STREAMLIT_PID · 日志: /tmp/alphaforge-streamlit.log"

# 5. 等就绪
for i in {1..15}; do
  if env no_proxy="127.0.0.1,localhost" curl -sf -o /dev/null \
       http://127.0.0.1:8501/_stcore/health 2>/dev/null; then
    echo "✓ Streamlit 已就绪"
    break
  fi
  sleep 1
done

# 6. 可选：ngrok 公网隧道
if [[ "${1:-}" == "--tunnel" ]]; then
  if ! command -v ngrok >/dev/null 2>&1; then
    echo "✗ 未安装 ngrok。brew install ngrok 后再试。"
    exit 1
  fi
  echo "🌐 启动 ngrok 公网隧道..."
  ngrok http 8501
fi

echo ""
echo "💡 浏览器打开：http://127.0.0.1:8501"
echo "🛑 关闭：kill $STREAMLIT_PID"

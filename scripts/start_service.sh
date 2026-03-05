#!/usr/bin/env bash
set -euo pipefail

SERVICE_TYPE="${SERVICE_TYPE:-lead-bot}"
PORT="${PORT:-8001}"
HOST="${HOST:-0.0.0.0}"

case "${SERVICE_TYPE}" in
  lead-bot)
    exec python -m uvicorn bots.lead_bot.main:app --host "${HOST}" --port "${PORT}"
    ;;
  seller-bot)
    exec python -m uvicorn bots.seller_bot.main:app --host "${HOST}" --port "${PORT}"
    ;;
  buyer-bot)
    exec python -m uvicorn bots.buyer_bot.main:app --host "${HOST}" --port "${PORT}"
    ;;
  dashboard)
    exec streamlit run command_center/dashboard_v3.py \
      --server.address "${HOST}" \
      --server.port "${PORT}" \
      --server.headless true
    ;;
  launcher)
    exec python jorge_launcher.py
    ;;
  *)
    echo "Unknown SERVICE_TYPE='${SERVICE_TYPE}'. Use: lead-bot|seller-bot|buyer-bot|dashboard|launcher" >&2
    exit 1
    ;;
esac

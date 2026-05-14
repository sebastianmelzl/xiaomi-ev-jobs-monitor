#!/usr/bin/env bash
set -e

PROJ="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJ"

# ── Python environment ────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "→ Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# ── Playwright browsers ───────────────────────────────────────────────────────
if ! python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.stop()" 2>/dev/null; then
  echo "→ Installing Playwright browsers..."
  playwright install chromium
fi

# ── Environment ───────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  echo "→ Creating .env from .env.example..."
  cp .env.example .env
  echo "   Edit .env to customize settings."
fi

# ── Database ──────────────────────────────────────────────────────────────────
mkdir -p data logs

# ── Start ─────────────────────────────────────────────────────────────────────
HOST="${APP_HOST:-127.0.0.1}"
PORT="${APP_PORT:-8000}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ⚡ Xiaomi EV Jobs Monitor"
echo "  → http://${HOST}:${PORT}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

uvicorn app.main:app --host "$HOST" --port "$PORT" --reload

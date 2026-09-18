#!/usr/bin/env bash
# Build the OpenArcade .venv with ALL deps (runtime + test + mcp) plus the
# Playwright + arm64 Chromium needed by the self-verify screenshot harness
# (tools/shoot.py). Idempotent — safe to re-run. Usage: ./setup.sh
#
# Why explicit deps (not `uv pip install -e .`): the hatch-polylith-bricks build
# backend + editable install is finicky; the bricks are already wired onto
# PYTHONPATH by run.sh/run_web.sh, so we only need the third-party deps here.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${DIR}"

echo "==> Creating .venv"
uv venv .venv

echo "==> Installing runtime + test + mcp + dev deps"
VIRTUAL_ENV="${DIR}/.venv" uv pip install \
  "flet>=0.85.3" "flet-desktop>=0.85.3" "flet-video>=0.85.3" "flet-web>=0.85.3" \
  "pydantic>=2.0.0" "structlog>=25.1.0" "typer>=0.12.0" "pyyaml>=6.0" \
  "pytest>=8.0.0" "pytest-asyncio>=0.23.0" \
  "fastmcp>=2" \
  "playwright>=1.61.0"

echo "==> Installing Chromium for Playwright (self-verify screenshots)"
"${DIR}/.venv/bin/python" -m playwright install chromium

echo "==> Done. Run the app:   ./run.sh"
echo "    Web + screenshot:    ./run_web.sh   /   .venv/bin/python tools/shoot.py"

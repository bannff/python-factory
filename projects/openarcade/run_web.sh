#!/usr/bin/env bash
# Serve OpenArcade as a localhost web page (visual self-verification loop).
# Bound to 127.0.0.1 only. Usage: ./run_web.sh [--open]   (port via OPENARCADE_WEB_PORT, default 8550)
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="${DIR}:${DIR}/../../components/curator/src:${DIR}/../../components/ui/src:${DIR}/../../components/launch/src:${DIR}/../../components/library/src:${DIR}/../../components/arcade_config/src:${DIR}/../../components/state/src"
cd "${DIR}"
exec "${DIR}/.venv/bin/python" -m wall.app web "$@"

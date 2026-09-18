#!/usr/bin/env bash
# Launch the OpenArcade Flet game-wall window. Usage: ./run.sh
# Sets PYTHONPATH to the project + every brick src the app needs, then runs the
# native Flet window. (wall.app currently needs factory.curator; ui/others added
# defensively so this keeps working as the app grows.)
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="${DIR}:${DIR}/../../components/curator/src:${DIR}/../../components/ui/src:${DIR}/../../components/launch/src:${DIR}/../../components/library/src:${DIR}/../../components/arcade_config/src:${DIR}/../../components/state/src"
cd "${DIR}"
exec "${DIR}/.venv/bin/python" -m wall.app "$@"

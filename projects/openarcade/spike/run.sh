#!/usr/bin/env bash
# Run the NCI handoff spike from the project venv with correct paths.
# Usage: ./spike/run.sh [--real HOST:PORT]
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
# Project dir (for the `spike` package) + every brick src on the path.
export PYTHONPATH="${DIR}:${DIR}/../../components/launch/src:${DIR}/../../components/ui/src:${DIR}/../../components/evals/src:${DIR}/../../components/library/src:${DIR}/../../components/arcade_config/src:${DIR}/../../components/state/src"
cd "${DIR}"
exec "${DIR}/.venv/bin/python" -m spike.nci_handoff_spike "$@"

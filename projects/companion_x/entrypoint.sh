#!/bin/sh
# Companion-X container entrypoint — supports multiple run modes.
#
# RUN_MODE controls which process starts:
#   unified — unified MCP+API server (default, same as api)
#   api     — alias for unified
#   mcp     — MCP aggregator server (stdio)
#   worker  — SQS long-poll worker (Fargate)
#
# Worker mode requires: SQS_QUEUE_URL, optionally AWS_REGION (default us-east-1)

set -e

RUN_MODE="${RUN_MODE:-api}"

case "$RUN_MODE" in
  unified|api)
    exec python /app/main.py
    ;;
  mcp)
    export EAGER_LOAD=1
    exec python -c "from factory.mcp_server.core import main; main()"
    ;;
  worker)
    if [ -z "$SQS_QUEUE_URL" ]; then
      echo "ERROR: SQS_QUEUE_URL required for worker mode" >&2
      exit 1
    fi
    exec python -c "
from factory.worker.runtime.runtime import get_runtime
rt = get_runtime(backend='fargate_sqs', broker_url='${SQS_QUEUE_URL}')
rt.start()
"
    ;;
  *)
    echo "ERROR: Unknown RUN_MODE=$RUN_MODE (expected: unified, api, mcp, worker)" >&2
    exit 1
    ;;
esac

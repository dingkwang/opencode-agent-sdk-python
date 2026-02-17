#!/bin/bash
set -e

PORT=54321

echo "[entrypoint] Starting opencode serve on port $PORT ..."
cd /workspace
opencode serve --port $PORT 2>/tmp/opencode.log &
OPENCODE_PID=$!

# Wait for the server to accept connections
echo "[entrypoint] Waiting for server ..."
for i in $(seq 1 30); do
  if curl -sf -X POST http://127.0.0.1:$PORT/session -o /dev/null 2>/dev/null; then
    echo "[entrypoint] Server ready (${i}s)"
    break
  fi
  if ! kill -0 $OPENCODE_PID 2>/dev/null; then
    echo "[entrypoint] opencode serve exited unexpectedly"
    cat /tmp/opencode.log
    exit 1
  fi
  sleep 1
done

# Run the test
echo "[entrypoint] Running SDK test ..."
export OPENCODE_SERVER_URL="http://127.0.0.1:$PORT"
uv run --project /sdk python /sdk/test_sdk_docker.py
EXIT_CODE=$?

# Cleanup
kill $OPENCODE_PID 2>/dev/null || true
exit $EXIT_CODE

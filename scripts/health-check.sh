#!/bin/bash
set -euo pipefail

systemctl is-active --quiet safelock-api

for i in {1..10}; do
  if curl -fsS http://localhost:8090/status >/dev/null; then
    exit 0
  fi
  sleep 2
done

exit 1

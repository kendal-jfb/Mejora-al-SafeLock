#!/bin/bash
set -euo pipefail

systemctl is-active --quiet safelock-api
curl -fsS http://localhost:8090/status >/dev/null

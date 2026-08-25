#!/usr/bin/env bash
# Vast.ai instance onstart — paste as the instance "On-start script" (or call from it).
# Ensures fleet supervisor + worker come up whenever the instance boots.
# Dashboard start (VAST_API_KEY) only works if this runs after boot.
set -euo pipefail
cd /workspace/BPO_AI_Agent/agent
# Prefer project venv when present
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
exec bash scripts/restart_fleet_supervisor.sh

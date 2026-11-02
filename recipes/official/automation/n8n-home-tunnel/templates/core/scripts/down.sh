#!/usr/bin/env bash
# トンネルと n8n を止める(データは残る。消すのは teardown.sh)
set -euo pipefail
source "$(dirname "$0")/_env.sh"
load_env

if pid="$(tunnel_pid)"; then
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  ok "トンネルを停止(PID $pid)"
else
  ok "トンネルは停止済み"
fi
rm -f "$PID_FILE"

if docker info >/dev/null 2>&1; then
  docker compose stop
  ok "n8n を停止(データは $N8N_VOLUME に残っています)"
else
  ok "Docker が止まっているので n8n も停止済み"
fi

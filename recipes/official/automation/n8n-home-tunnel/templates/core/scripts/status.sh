#!/usr/bin/env bash
# 状態の点検: n8n(手元)/ オーナー作成 / トンネル / 公開 URL
set -uo pipefail
source "$(dirname "$0")/_env.sh"
load_env

say "== $N8N_INSTANCE の状態 =="
if docker info >/dev/null 2>&1; then
  state="$(docker inspect -f '{{.State.Status}}' "$N8N_INSTANCE" 2>/dev/null || echo 'なし')"
  [ "$state" = "running" ] && ok "コンテナ: running" || ng "コンテナ: $state"
  ver="$(docker inspect -f '{{.Config.Image}}' "$N8N_INSTANCE" 2>/dev/null | sed 's/.*://')"
  [ -n "$ver" ] && say "        バージョン: $ver"
else
  ng "Docker Desktop が起動していません"
fi

if curl -fsS -m 3 "$LOCAL_URL/healthz" >/dev/null 2>&1; then ok "手元: $LOCAL_URL"; else ng "手元: $LOCAL_URL に応答なし"; fi

rc=0; owner_ready || rc=$?
case "$rc" in
  0) ok "オーナー: 作成済み" ;;
  1) ng "オーナー: 未作成($LOCAL_URL を開いて作成。作るまで公開しません)" ;;
  *) say "  --    オーナー: 確認できず(n8n が止まっている)" ;;
esac

if pid="$(tunnel_pid)"; then ok "トンネル: 起動中(PID $pid)"; else ng "トンネル: 停止"; fi

code="$(curl -s -o /dev/null -w '%{http_code}' -m 8 "https://$N8N_HOST/healthz" || true)"
if [ "$code" = "200" ]; then ok "公開: https://$N8N_HOST/"; else ng "公開: https://$N8N_HOST/ → HTTP ${code:-なし}"; fi

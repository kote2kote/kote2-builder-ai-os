#!/usr/bin/env bash
# TEST-004 / 006 / 007: 動いている n8n の実地確認(setup.sh と up.sh の後に実行)
#   local  = 手元の healthz
#   public = 公開 URL の healthz(ステータスだけでなく本文まで見る = PIT-CFTUNNEL-002)
#   mcp    = MCP の入口が有効(401 = 認証待ち。404 = 未有効 = PIT-N8N-002)
# cwd = 生成プロジェクト直下。exit 0 = PASS。値は .env からスクリプトが読む(画面に出さない)
set -u
# shellcheck disable=SC1091
source scripts/_env.sh
load_env
case "${1:-}" in
  local)
    body="$(curl -fsS -m 5 "$LOCAL_URL/healthz" 2>/dev/null)" || { echo "NG: 手元の n8n が応答しない"; exit 1; }
    case "$body" in *'"ok"'*) echo "PASS: 手元 $LOCAL_URL";; *) echo "NG: 手元の応答が n8n ではない"; exit 1;; esac ;;
  public)
    body="$(curl -fsS -m 10 "https://$N8N_HOST/healthz" 2>/dev/null)" || { echo "NG: 公開 URL が応答しない"; exit 1; }
    case "$body" in *'"ok"'*) echo "PASS: 公開 https://$N8N_HOST/";; *) echo "NG: 公開 URL の中身が n8n ではない(別のサービスにつながっている)"; exit 1;; esac ;;
  mcp)
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 10 -X POST -H 'Content-Type: application/json' -d '{}' "https://$N8N_HOST/mcp-server/http")"
    case "$code" in
      401) echo "PASS: MCP 有効(認証待ち)";;
      404) echo "NG: MCP が未有効(n8n の Settings > Instance-level MCP で Enable)"; exit 1;;
      *)   echo "NG: MCP の入口が想定外の応答(HTTP $code)"; exit 1;;
    esac ;;
  *) echo "使い方: check-live.sh local|public|mcp"; exit 2 ;;
esac

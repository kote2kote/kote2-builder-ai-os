#!/usr/bin/env bash
# fake-pnpm.sh — TEST-022 用の疑似 `pnpm exec wrangler`。クラウドには一切触らない。
#   FAKE_NAME   = wrangler.jsonc の name(存在判定に使う)
#   FAKE_EXISTS = r2,kv,ai のうち「既にある」もの(カンマ区切り)
#   FAKE_FAIL   = list-r2 / list-kv / list-ai / badjson / r2-unknown / r2-empty / kv-noid-list / create-r2 / create-kv / kv-noid / create-ai
#   FAKE_LOG    = 呼ばれた作成コマンドを 1 行ずつ追記するファイル
shift 2 2>/dev/null || true   # "exec wrangler" を読み飛ばす
N="${FAKE_NAME:?FAKE_NAME を設定してください}"
has()   { [[ ",${FAKE_EXISTS:-}," == *",$1,"* ]]; }
fails() { [[ ",${FAKE_FAIL:-}," == *",$1,"* ]]; }
log()   { [[ -n "${FAKE_LOG:-}" ]] && echo "$*" >> "$FAKE_LOG"; }
case "$1 $2 ${3:-}" in
  "whoami"*) echo "👋 You are logged in with an OAuth Token, associated with the email fake@example.com."; exit 0 ;;
  "r2 bucket list")
    log "list-r2"; fails list-r2 && { echo "APIError"; exit 7; }
    fails r2-unknown && { echo "Buckets:"; echo "  * something-else"; exit 0; }
    echo "Listing buckets..."; fails r2-empty && exit 0
    has r2 && echo "name:           ${N}-docs"; echo "name:           other-bucket"; exit 0 ;;
  "kv namespace list")
    log "list-kv"; fails list-kv && { echo "APIError"; exit 7; }
    fails badjson && { echo "not json"; exit 0; }
    fails kv-noid-list && { echo "[{\"title\":\"${N}-REGISTRY\"},{\"id\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"title\":\"other\"}]"; exit 0; }
    if has kv; then echo "[{\"id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"title\":\"${N}-REGISTRY\"},{\"id\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"title\":\"other\"}]"
    else echo "[{\"id\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"title\":\"other\"}]"; fi; exit 0 ;;
  "ai-search list"*)
    log "list-ai"; fails list-ai && { echo "APIError"; exit 7; }
    if [[ " $* " == *" --json "* ]]; then
      if has ai; then echo "[{\"id\":\"${N}\",\"type\":\"r2\"},{\"id\":\"other-instance\",\"type\":\"r2\"}]"; else echo "[{\"id\":\"other-instance\",\"type\":\"r2\"}]"; fi
    else has ai && echo "│ ${N} │ r2 │"; echo "│ other-instance │ r2 │"; fi; exit 0 ;;
  "r2 bucket create") log "create-r2 $4"; fails create-r2 && { echo "create failed"; exit 7; }; echo "Created bucket"; exit 0 ;;
  "kv namespace create") log "create-kv $4"; fails create-kv && { echo "create failed"; exit 7; }; fails kv-noid && { echo "created (no id printed)"; exit 0; }
    echo "{ \"binding\": \"REGISTRY\", \"id\": \"cccccccccccccccccccccccccccccccc\" }"; exit 0 ;;
  "ai-search create"*) log "create-ai $3"; fails create-ai && { echo "create failed"; exit 7; }; echo "created"; exit 0 ;;
  *) echo "fake-pnpm: unknown command: $*" >&2; exit 9 ;;
esac

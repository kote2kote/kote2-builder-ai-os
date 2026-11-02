#!/usr/bin/env bash
# TEST-002: マシンごとの値がどこにも直書きされておらず、別のマシン用の値を入れれば別物ができるか
# cwd = 生成プロジェクト直下。exit 0 = PASS
set -u
fail=0; ng() { echo "NG: $*"; fail=1; }

# 1) .env.example の「マシン別の値」が、スクリプト・compose・スキルに直書きされていない
for v in N8N_HOST TUNNEL_NAME MCP_NAME N8N_INSTANCE N8N_VOLUME; do
  val="$(grep -E "^$v=" .env.example | head -1 | cut -d= -f2-)"
  [ -n "$val" ] || continue
  hits="$(grep -rlF -- "$val" compose.yaml scripts cloudflared/config.example.yml .claude/skills/n8n-env 2>/dev/null)"
  [ -z "$hits" ] || ng "$v の値が直書きされている: $hits"
done

# 2) 2 台ぶんの値で MCP 登録を作り、名前も URL も別になるか(setup.sh と同じ関数を使う)
tmpd="$(mktemp -d)"
(
  # shellcheck disable=SC1091
  source scripts/_env.sh >/dev/null 2>&1
  MCP_NAME=machine-a N8N_HOST=n8n-a.example.com write_mcp_json "$tmpd/a.json"
  MCP_NAME=machine-b N8N_HOST=n8n-b.example.com write_mcp_json "$tmpd/b.json"
)
for m in a b; do
  f="$tmpd/$m.json"
  [ -s "$f" ] || { ng "machine-$m の .mcp.json が作られない"; continue; }
  grep -q "\"machine-$m\"" "$f" || ng "machine-$m の MCP 名が入っていない"
  grep -q "https://n8n-$m.example.com/mcp-server/http" "$f" || ng "machine-$m の URL が違う"
  if command -v node >/dev/null 2>&1; then
    node -e "JSON.parse(require('fs').readFileSync(process.argv[1],'utf8'))" "$f" 2>/dev/null || ng "machine-$m の .mcp.json が JSON として壊れている"
  fi
done
rm -rf "$tmpd"

# 3) トンネル設定のひな型が、マシンごとの 4 つの値だけで組み立てられる
for t in __TUNNEL_ID__ __CREDENTIALS_FILE__ __N8N_HOST__ __N8N_LOCAL_PORT__; do
  grep -q "$t" cloudflared/config.example.yml || ng "config.example.yml に $t がない"
done

[ "$fail" -eq 0 ] && echo "PASS: マシン別の値は .env だけにある"; exit "$fail"

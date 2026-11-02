#!/usr/bin/env bash
# TEST-001: 生成物の土台が揃っているか(n8n もトンネルも起動しない静的検査)
# cwd = 生成プロジェクト直下。exit 0 = PASS
set -u
fail=0; ng() { echo "NG: $*"; fail=1; }

for f in compose.yaml .env.example .gitignore cloudflared/config.example.yml cloudflared/admin.yml \
         scripts/_env.sh scripts/setup.sh scripts/up.sh scripts/down.sh scripts/status.sh \
         .claude/skills/n8n-env/SKILL.md; do
  [ -f "$f" ] || ng "$f がない"
done

for f in scripts/*.sh; do bash -n "$f" 2>/dev/null || ng "$f の構文エラー"; done

# プレースホルダの置き忘れ
# ({{.State.Status}} のような docker の書式指定は対象外。{{大文字_名前}} だけを見る)
left="$(grep -rlE '\{\{[A-Z][A-Z0-9_]*\}\}' compose.yaml .env.example scripts cloudflared .claude/skills/n8n-env 2>/dev/null | tr '\n' ' ')"
[ -z "$left" ] || ng "{{...}} が残っている: $left"

# 秘密と、このマシン専用の生成物を Git に載せない
for p in '.env' 'cloudflared/config.yml' 'cloudflared/run/'; do
  grep -qxF "$p" .gitignore || ng ".gitignore に $p がない"
done

# LAN に出さない(127.0.0.1 だけで待ち受け)
grep -q '"127.0.0.1:${N8N_LOCAL_PORT' compose.yaml || ng "compose.yaml が 127.0.0.1 だけで待ち受けていない"

# マシンごとの値はすべて .env に必須で求める(既定値でごまかさない)
for v in N8N_HOST TUNNEL_NAME MCP_NAME N8N_INSTANCE N8N_VOLUME N8N_LOCAL_PORT N8N_VERSION; do
  grep -qE "^$v=.+" .env.example || ng ".env.example の $v が空"
done

# compose を仮の暗号化キーで展開できるか(Docker の CLI だけ使う。起動はしない)
if command -v docker >/dev/null 2>&1; then
  tmp="$(mktemp)"; sed 's/^N8N_ENCRYPTION_KEY=$/N8N_ENCRYPTION_KEY=dummy-for-test/' .env.example > "$tmp"
  docker compose --env-file "$tmp" -f compose.yaml config -q 2>/dev/null || ng "compose.yaml を展開できない"
  rm -f "$tmp"
else
  ng "docker が無い(Docker Desktop が必要)"
fi

[ "$fail" -eq 0 ] && echo "PASS: 静的検査"; exit "$fail"

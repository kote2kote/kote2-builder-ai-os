#!/usr/bin/env bash
# n8n を起動 → オーナー作成済みならトンネルも起動して公開する
set -euo pipefail
source "$(dirname "$0")/_env.sh"
load_env
docker_up
need cloudflared "Mac: brew install cloudflared / Windows: winget install --id Cloudflare.cloudflared"
[ -f "$CF_CONFIG" ] || die "cloudflared/config.yml がありません。先に bash scripts/setup.sh を実行してください"

say "== n8n を起動 =="
docker compose up -d --quiet-pull

printf '  起動待ち'
for _ in $(seq 1 60); do
  curl -fsS -m 2 "$LOCAL_URL/healthz" >/dev/null 2>&1 && break
  printf '.'; sleep 2
done
echo
curl -fsS -m 2 "$LOCAL_URL/healthz" >/dev/null 2>&1 || die "n8n が応答しません。docker compose logs n8n で原因を確認してください"
ok "n8n: $LOCAL_URL"

# オーナー未作成のまま公開しない(最初に開いた人がオーナーになれてしまうため)
# healthz が通っても API の準備が数秒遅れるので、判定できるまで少し待つ
rc=2
for _ in $(seq 1 15); do
  rc=0; owner_ready || rc=$?
  [ "$rc" -ne 2 ] && break
  sleep 2
done
if [ "$rc" -eq 1 ]; then
  say ""
  say "まだ公開していません。先にこのマシンのブラウザで $LOCAL_URL を開き、オーナーアカウントを作ってください。"
  say "作り終えたら、もう一度 bash scripts/up.sh を実行すると公開されます。"
  exit 0
elif [ "$rc" -eq 2 ]; then
  die "オーナー作成済みかを確認できませんでした(安全のため公開しません)"
fi
ok "オーナー作成済み"

say "== トンネルを起動 =="
if pid="$(tunnel_pid)"; then
  ok "トンネルは起動済み(PID $pid)"
else
  mkdir -p "$RUN_DIR"
  nohup cloudflared tunnel --config "$CF_CONFIG" --no-autoupdate --logfile "$LOG_FILE" run >/dev/null 2>&1 &
  echo $! > "$PID_FILE"
  sleep 3
  tunnel_pid >/dev/null || die "トンネルがすぐに止まりました。cloudflared/run/cloudflared.log を確認してください"
  ok "トンネル起動(PID $(cat "$PID_FILE"))"
fi

printf '  公開 URL の確認中'
code=""
for _ in $(seq 1 15); do
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 5 "https://$N8N_HOST/healthz" || true)"
  [ "$code" = "200" ] && break
  printf '.'; sleep 2
done
echo
if [ "$code" = "200" ]; then
  ok "公開: https://$N8N_HOST/"
else
  ng "公開 URL がまだ 200 を返しません(HTTP $code)。数十秒待って bash scripts/status.sh で再確認してください"
fi

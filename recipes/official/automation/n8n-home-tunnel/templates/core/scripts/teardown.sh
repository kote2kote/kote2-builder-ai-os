#!/usr/bin/env bash
# 一時環境の片付け: 停止 → トンネル削除 → (希望すれば)データ削除
# DNS レコードは cloudflared から消せないので、最後に削除場所を案内する
set -euo pipefail
source "$(dirname "$0")/_env.sh"
load_env

say "== 片付け(元に戻せません)=="
say "  止めるもの  : n8n とトンネル"
say "  消すもの    : Cloudflare のトンネル「$TUNNEL_NAME」"
say "  選べるもの  : n8n のデータ(ワークフロー・認証情報。ボリューム $N8N_VOLUME)"
say ""
printf '続けるならトンネル名「%s」を入力してください: ' "$TUNNEL_NAME"
read -r answer
[ "$answer" = "$TUNNEL_NAME" ] || die "入力が一致しないので何もしませんでした"

bash "$ROOT/scripts/down.sh"

CERT=""
for d in "$HOME/.cloudflared" "$HOME/.cloudflare-warp" "$HOME/cloudflare-warp"; do
  [ -f "$d/cert.pem" ] && { CERT="$d/cert.pem"; break; }
done
if [ -n "$CERT" ]; then
  cf() { cloudflared tunnel --config "$CF_DIR/admin.yml" --origincert "$CERT" "$@"; }
  cf cleanup "$TUNNEL_NAME" >/dev/null 2>&1 || true
  if cf delete "$TUNNEL_NAME" >/dev/null 2>&1; then ok "トンネル $TUNNEL_NAME を削除"; else ng "トンネル削除に失敗(既に無い可能性)"; fi
else
  ng "Cloudflare 証明書が無いのでトンネルは消していません"
fi
rm -f "$CF_CONFIG"

printf 'n8n のデータも消しますか?(消す前に workflows/ へ書き出しておくのがおすすめ) [yes/No]: '
read -r answer
if [ "$answer" = "yes" ]; then
  docker compose down -v
  ok "コンテナとデータ($N8N_VOLUME)を削除"
else
  docker compose down >/dev/null 2>&1 || true
  ok "データは残しました(ボリューム $N8N_VOLUME)"
fi

say ""
say "最後に 1 つだけ手作業: Cloudflare ダッシュボード → このドメインの DNS で"
say "  $N8N_HOST の CNAME レコードを削除してください(cloudflared からは消せません)"

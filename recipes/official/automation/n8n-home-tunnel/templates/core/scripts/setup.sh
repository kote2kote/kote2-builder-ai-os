#!/usr/bin/env bash
# 初回だけ実行: .env の作成 → 暗号化キーの生成 → トンネル作成 → DNS 登録 → トンネル設定の書き出し
# 何度実行しても安全(作成済みのものは作り直さない)。既存の常設トンネルや DNS は上書きしない。
set -euo pipefail
source "$(dirname "$0")/_env.sh"

say "== n8n セットアップ =="

need cloudflared "Mac: brew install cloudflared / Windows: winget install --id Cloudflare.cloudflared"
need openssl "暗号化キーの生成に使います"

# 1. .env を用意
if [ ! -f .env ]; then
  cp .env.example .env
  ok ".env を .env.example から作成"
else
  ok ".env は作成済み"
fi

# 2. 暗号化キー(空の時だけ生成。値は表示しない)
if grep -qE '^N8N_ENCRYPTION_KEY=$' .env; then
  key="$(openssl rand -hex 32)"
  tmp="$(mktemp)"
  awk -v k="$key" '/^N8N_ENCRYPTION_KEY=$/{print "N8N_ENCRYPTION_KEY=" k; next} {print}' .env > "$tmp"
  cat "$tmp" > .env && rm -f "$tmp"
  unset key
  ok "暗号化キーを生成して .env に保存(画面には出しません)"
else
  ok "暗号化キーは設定済み(変更しません)"
fi

load_env

# 3. Cloudflare へのログイン証明書(cert.pem)
CERT=""
for d in "$HOME/.cloudflared" "$HOME/.cloudflare-warp" "$HOME/cloudflare-warp"; do
  [ -f "$d/cert.pem" ] && { CERT="$d/cert.pem"; break; }
done
if [ -z "$CERT" ]; then
  say "Cloudflare へのログインが必要です。ブラウザが開くので、公開 URL のドメインを選んで許可してください"
  cloudflared tunnel --config "$CF_DIR/admin.yml" login
  CERT="$HOME/.cloudflared/cert.pem"
fi
ok "Cloudflare 証明書あり"

# cloudflared の管理コマンドは既存の ~/.cloudflared/config.yml を読まないよう、中身の無い admin.yml を明示(/dev/null は「空の設定」エラーになる)
cf() { cloudflared tunnel --config "$CF_DIR/admin.yml" --origincert "$CERT" "$@"; }

# 4. トンネル(名前で探し、無ければ作る)
find_id() {
  cf list --name "$TUNNEL_NAME" --output json 2>/dev/null \
    | tr -d '\n ' | grep -oE '"id":"[0-9a-f-]{36}"' | head -1 | cut -d'"' -f4
}
TUNNEL_ID="$(find_id || true)"
if [ -z "$TUNNEL_ID" ]; then
  cf create "$TUNNEL_NAME" >/dev/null
  TUNNEL_ID="$(find_id || true)"
  [ -n "$TUNNEL_ID" ] || die "トンネル $TUNNEL_NAME の作成を確認できませんでした"
  ok "トンネル $TUNNEL_NAME を作成"
else
  ok "トンネル $TUNNEL_NAME は作成済み"
fi

CRED="$(dirname "$CERT")/$TUNNEL_ID.json"
[ -f "$CRED" ] || die "トンネルの認証ファイルが見つかりません($TUNNEL_NAME)。別のマシンで作ったトンネルなら、このマシン用に TUNNEL_NAME を変えて作り直してください"

# 5. DNS(上書きしない。既に同じ名前のレコードがあれば止まる)
if out="$(cf route dns "$TUNNEL_ID" "$N8N_HOST" 2>&1)"; then
  case "$out" in
    # ホスト名の直後が空白であることまで見る(ログインしたドメインが違うと「名前.別ドメイン」で登録されるため)
    *"$N8N_HOST is already configured"*) ok "DNS: $N8N_HOST は登録済み" ;;
    *"CNAME $N8N_HOST "*) ok "DNS: $N8N_HOST をこのトンネルへ向けました" ;;
    *) printf '%s\n' "$out"; die "DNS の登録先が $N8N_HOST と一致しません。Cloudflare のログインで選んだドメインを確認してください" ;;
  esac
else
  case "$out" in
    *"already configured to route to your tunnel"*) ok "DNS: $N8N_HOST は登録済み" ;;
    *"already exists"*|*"already configured"*)
      printf '%s\n' "$out"
      die "$N8N_HOST は別の用途で使われています。上書きはしません。.env の N8N_HOST を別の名前に変えて再実行してください" ;;
    *) printf '%s\n' "$out"; die "DNS の登録に失敗しました" ;;
  esac
fi

# 6. このマシン専用のトンネル設定を書き出す
mkdir -p "$RUN_DIR"
sed -e "s|__TUNNEL_ID__|$TUNNEL_ID|" \
    -e "s|__CREDENTIALS_FILE__|$(native_path "$CRED")|" \
    -e "s|__N8N_HOST__|$N8N_HOST|" \
    -e "s|__N8N_LOCAL_PORT__|$N8N_LOCAL_PORT|" \
    "$CF_DIR/config.example.yml" > "$CF_CONFIG"
ok "トンネル設定を cloudflared/config.yml に書き出し"

# 7. Claude Code 用の MCP 登録(このマシンの名前と URL で作る。既にあれば触らない)
if [ -f .mcp.json ]; then
  ok ".mcp.json は作成済み(変更しません)"
else
  write_mcp_json .mcp.json
  ok ".mcp.json を作成(MCP 名 $MCP_NAME → https://$N8N_HOST/mcp-server/http)"
fi

say ""
say "セットアップ完了。次は: bash scripts/up.sh"
say "(MCP を使う時は n8n の Settings > Instance-level MCP で Enable → Claude Code の /mcp で $MCP_NAME を認証)"

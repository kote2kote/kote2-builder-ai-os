# scripts/*.sh 共通の下ごしらえ(直接は実行しない。source して使う)
# - プロジェクト直下へ移動し、.env を読み込む
# - 値は表示しない(秘密値を画面・ログに出さない)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

CF_DIR="$ROOT/cloudflared"
CF_CONFIG="$CF_DIR/config.yml"
RUN_DIR="$CF_DIR/run"
PID_FILE="$RUN_DIR/cloudflared.pid"
LOG_FILE="$RUN_DIR/cloudflared.log"

say()  { printf '%s\n' "$*"; }
ok()   { printf '  OK    %s\n' "$*"; }
ng()   { printf '  NG    %s\n' "$*"; }
die()  { printf '\n中止: %s\n' "$*" >&2; exit 1; }

load_env() {
  [ -f "$ROOT/.env" ] || die ".env がありません。先に bash scripts/setup.sh を実行してください"
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
  : "${N8N_HOST:?N8N_HOST が .env にありません}"
  : "${TUNNEL_NAME:?TUNNEL_NAME が .env にありません}"
  : "${N8N_INSTANCE:?N8N_INSTANCE が .env にありません}"
  : "${N8N_VOLUME:?N8N_VOLUME が .env にありません}"
  : "${N8N_LOCAL_PORT:?N8N_LOCAL_PORT が .env にありません}"
  LOCAL_URL="http://127.0.0.1:${N8N_LOCAL_PORT}"
}

need() { command -v "$1" >/dev/null 2>&1 || die "$1 が見つかりません($2)"; }

docker_up() {
  need docker "Docker Desktop を入れてください。README の「必要なもの」参照"
  docker info >/dev/null 2>&1 || die "Docker Desktop が起動していません。アプリを起動してから、もう一度実行してください"
}

# Windows(Git Bash)では cloudflared.exe が Git Bash 形式のパス(/c/... で始まる)を読めないので、設定ファイルに書くパスだけ変換する
native_path() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

# Claude Code 用の MCP 登録ファイルを、このマシンの名前と URL で書く(引数: 出力先)
write_mcp_json() {
  printf '{\n  "mcpServers": {\n    "%s": {\n      "type": "http",\n      "url": "https://%s/mcp-server/http"\n    }\n  }\n}\n' \
    "${MCP_NAME:?MCP_NAME が .env にありません}" "${N8N_HOST:?}" > "$1"
}

# 自分が起動した cloudflared が生きているか(PID ファイル基準。他のトンネルには触らない)
tunnel_pid() {
  [ -f "$PID_FILE" ] || return 1
  local pid; pid="$(cat "$PID_FILE" 2>/dev/null)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && { printf '%s' "$pid"; return 0; }
  return 1
}

# n8n の初期セットアップ(オーナー作成)が済んでいるか。済んでいれば 0
# 未作成のまま公開すると、最初に URL を開いた人がオーナーになれてしまう
owner_ready() {
  local body
  body="$(curl -fsS -m 5 "$LOCAL_URL/rest/settings" 2>/dev/null)" || return 2
  case "$body" in
    *'"showSetupOnFirstLoad":true'*)  return 1 ;;
    *'"showSetupOnFirstLoad":false'*) return 0 ;;
    *) return 2 ;;
  esac
}

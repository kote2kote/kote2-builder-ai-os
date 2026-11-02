#!/usr/bin/env bash
# ============================================================
# send-test.sh — 各チャネルへのテスト送信(出口はこの 1 本に封じる = CORE-05)
# ------------------------------------------------------------
# 使い方:
#   bash scripts/send-test.sh slack    "#general"      "テストです"
#   bash scripts/send-test.sh chatwork "ルームID"       "テストです"
#   bash scripts/send-test.sh line     "ユーザーID(U..)" "テストです"
#   bash scripts/send-test.sh discord  "チャンネルID"   "テストです"
#
# 鉄則: 送信は 1 回のみ。失敗してもこのスクリプトを連打しない
#       (重複投稿より欠損を選ぶ)。AI に curl を直接叩かせない。
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

# .env を読み込む(値はユーザー自身が記入したもの)
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
else
  echo "ERROR: .env がありません。.env.example をコピーして値を記入してください" >&2
  exit 1
fi

CHANNEL="${1:-}"
TARGET="${2:-}"
MESSAGE="${3:-{{PROJECT_NAME}} テスト送信です}"

if [ -z "$CHANNEL" ] || [ -z "$TARGET" ]; then
  echo "使い方: bash scripts/send-test.sh {slack|discord|chatwork|line} {送信先} [メッセージ]" >&2
  exit 1
fi

case "$CHANNEL" in
  slack)
    curl -sS -X POST "https://slack.com/api/chat.postMessage" \
      -H "Authorization: Bearer ${SLACK_BOT_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "$(printf '{"channel":"%s","text":"%s"}' "$TARGET" "$MESSAGE")"
    ;;
  discord)
    curl -sS -X POST "https://discord.com/api/v10/channels/${TARGET}/messages" \
      -H "Authorization: Bot ${DISCORD_BOT_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "$(printf '{"content":"%s"}' "$MESSAGE")"
    ;;
  chatwork)
    curl -sS -X POST "https://api.chatwork.com/v2/rooms/${TARGET}/messages" \
      -H "X-ChatWorkToken: ${CHATWORK_API_TOKEN}" \
      --data-urlencode "body=${MESSAGE}" \
      --data-urlencode "self_unread=0"
    ;;
  line)
    curl -sS -X POST "https://api.line.me/v2/bot/message/push" \
      -H "Authorization: Bearer ${LINE_CHANNEL_ACCESS_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "$(printf '{"to":"%s","messages":[{"type":"text","text":"%s"}]}' "$TARGET" "$MESSAGE")"
    ;;
  *)
    echo "ERROR: 未対応のチャネル: $CHANNEL(slack / discord / chatwork / line)" >&2
    exit 1
    ;;
esac

echo ""
echo "送信リクエストを 1 回実行しました(結果は上のレスポンスを確認)"

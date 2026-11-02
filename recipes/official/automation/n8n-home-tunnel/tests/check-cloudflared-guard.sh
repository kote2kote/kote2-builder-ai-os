#!/usr/bin/env bash
# TEST-003(PIT-CFTUNNEL-003 / 004 / 005 の回帰): cloudflared が既存の設定を読まない・DNS を上書きしない
# cwd = 生成プロジェクト直下。exit 0 = PASS
set -u
fail=0; ng() { echo "NG: $*"; fail=1; }

# 実行行(コメント以外)で cloudflared tunnel を呼ぶ所は、必ず --config を付けている
while IFS= read -r line; do
  case "$line" in *"--config"*) ;; *) ng "--config なしで cloudflared を呼んでいる: $line" ;; esac
done < <(grep -hE '^[^#]*cloudflared tunnel' scripts/*.sh)

grep -qE '^[^#]*--config /dev/null' scripts/*.sh && ng "--config /dev/null を使っている(PIT-CFTUNNEL-004)"
grep -qE '^[^#]*--overwrite-dns' scripts/*.sh && ng "DNS を上書きする --overwrite-dns を使っている(PIT-CFTUNNEL-005)"
grep -qE '^[a-z-]+:' cloudflared/admin.yml || ng "cloudflared/admin.yml が空(PIT-CFTUNNEL-004)"

[ "$fail" -eq 0 ] && echo "PASS: 既存のトンネル設定・DNS に触れない"; exit "$fail"

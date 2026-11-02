#!/usr/bin/env bash
# TEST-005: MP4 を書き出せるか(例の頭 2 秒だけ)。Chrome / Edge か ffmpeg が無ければ exit 3 = SKIP
set -u
SK="${EXPLAINER_DIR:-.claude/skills/explainer-video}"
command -v node >/dev/null || { echo "FAIL: node がありません"; exit 1; }
FF="${FFMPEG_PATH:-$(command -v ffmpeg || true)}"
[ -n "$FF" ] || { echo "SKIP: ffmpeg が無い(MP4 書き出しだけ使えない。HTML 再生は可)"; exit 3; }
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
log="$(node "$SK/engine/render-video.mjs" "$SK/examples/mcp/index.html" "$OUT/test.mp4" --from 0 --to 2 2>&1)"; code=$?
echo "$log"
echo "$log" | grep -q "Chrome / Edge / Chromium が見つかりません" && { echo "SKIP: Chrome / Edge が見つからない"; exit 3; }
[ $code -eq 0 ] && [ -s "$OUT/test.mp4" ] || { echo "FAIL: explainer-mp4(exit $code)"; exit 1; }
# 60 コマ・1920x1080 か(ffmpeg 自身で数える。ffprobe が無い環境もあるため)
info="$("$FF" -hide_banner -i "$OUT/test.mp4" -map 0:v:0 -c copy -f null - 2>&1)"
echo "$info" | grep -q "1920x1080" && echo "ok: 1920x1080" || { echo "FAIL: 解像度が 1920x1080 でない"; exit 1; }
frames="$(echo "$info" | grep -oE 'frame= *[0-9]+' | tail -n 1 | grep -oE '[0-9]+')"
[ "${frames:-0}" -eq 60 ] && echo "ok: 60 コマ(2 秒 × 30fps)" || { echo "FAIL: コマ数 ${frames:-?}(期待 60)"; exit 1; }
echo "PASS: explainer-mp4"

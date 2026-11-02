#!/usr/bin/env bash
# TEST-004: キャラ無し(index.html から character.js を外す)でも撮れるか。Chrome / Edge が無ければ exit 3 = SKIP
set -u
SK="${EXPLAINER_DIR:-.claude/skills/explainer-video}"
command -v node >/dev/null || { echo "FAIL: node がありません"; exit 1; }
T="$SK/examples/.test-nocat-$$"; OUT="${EXPLAINER_STILLS_DIR:-$(mktemp -d)}"
trap 'rm -rf "$T"; [ -z "${EXPLAINER_STILLS_DIR:-}" ] && rm -rf "$OUT"' EXIT
mkdir -p "$T"
grep -v 'character/character.js' "$SK/examples/mcp/index.html" > "$T/index.html"
cp "$SK/examples/mcp/scene.js" "$T/scene.js"
grep -q 'character.js' "$T/index.html" && { echo "FAIL: character.js の行を外せなかった"; exit 1; }
log="$(node "$SK/engine/render-video.mjs" "$T/index.html" --stills 1,25 --stills-dir "$OUT" 2>&1)"; code=$?
echo "$log"
echo "$log" | grep -q "Chrome / Edge / Chromium が見つかりません" && { echo "SKIP: Chrome / Edge が見つからない"; exit 3; }
[ $code -eq 0 ] && [ -f "$OUT/still-25.png" ] || { echo "FAIL: explainer-nocat(exit $code)"; exit 1; }
echo "PASS: explainer-nocat(静止画: $OUT)"

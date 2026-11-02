#!/usr/bin/env bash
# TEST-003: 場面データの書き間違い(無いポーズ・無い矢印・無い箱・無い絵・長さ超え)で、書き出しが止まるか。
# Chrome / Edge が無ければ exit 3 = SKIP
set -u
SK="${EXPLAINER_DIR:-.claude/skills/explainer-video}"
command -v node >/dev/null || { echo "FAIL: node がありません"; exit 1; }
T="$SK/examples/.test-guard-$$"; OUT="$(mktemp -d)"
trap 'rm -rf "$T" "$OUT"' EXIT
mkdir -p "$T"
cp "$SK/examples/mcp/index.html" "$T/index.html"
cat > "$T/scene.js" <<'JS'
window.VIDEO = {
  items: [{ id: 'a', x: 100, y: 100, w: 300, h: 120, icon: 'no-such-icon', html: '<div class="k">箱</div>' }],
  arrows: [{ id: 'A1', d: 'M400,160 L700,160' }],
  scenes: [
    { dur: 3, pose: 'no-such-pose', caption: 'ポーズ違い', cam: [960, 432, 1], at: [[.2, 'show', 'a'], [.5, 'draw', 'NO-ARROW']] },
    { dur: 2, pose: 'smile', caption: '長さ超え', cam: [960, 432, 1], at: [[.2, 'show', 'no-box'], [5, 'draw', 'A1']] },
  ],
};
JS
log="$(node "$SK/engine/render-video.mjs" "$T/index.html" --stills 1 --stills-dir "$OUT" 2>&1)"; code=$?
echo "$log"
echo "$log" | grep -q "Chrome / Edge / Chromium が見つかりません" && { echo "SKIP: Chrome / Edge が見つからない"; exit 3; }
fail=0
[ $code -ne 0 ] && echo "ok: 書き間違いで exit $code" || { echo "FAIL: 書き間違いがあるのに exit 0"; fail=1; }
for want in "no-such-pose" "NO-ARROW" "no-box" "no-such-icon" "場面の長さ"; do
  echo "$log" | grep -q -- "$want" && echo "ok: 「${want}」を指摘" || { echo "FAIL: 「${want}」の指摘が無い"; fail=1; }
done
ls "$OUT"/still-*.png >/dev/null 2>&1 && { echo "FAIL: 止まるべきなのに静止画を書き出した"; fail=1; }
[ $fail -eq 0 ] && echo "PASS: explainer-guard" || echo "FAIL: explainer-guard"
exit $fail

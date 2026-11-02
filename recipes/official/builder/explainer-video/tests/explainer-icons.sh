#!/usr/bin/env bash
# TEST-008: 同梱の絵(engine/icons.js)が全部描けて、絵柄の約束(色はクラスで塗る)を守っているか。
# 絵の一覧(references/icon-catalog)を静止画で撮る。Chrome / Edge が無ければ exit 3 = SKIP
set -u
SK="${EXPLAINER_DIR:-.claude/skills/explainer-video}"
command -v node >/dev/null || { echo "FAIL: node がありません"; exit 1; }
fail=0
# 数と絵柄の約束: 40 個以上 / 名前は英小文字 / 意味がある / 色を直接書かない(theme に追従させるため)
node -e '
global.window = {}; require(require("path").resolve(process.argv[1]));
const I = window.EXPLAINER_ICONS || {}, names = Object.keys(I); let bad = 0;
if (names.length < 40) { console.log(`FAIL: 絵が ${names.length} 個(40 個以上のはず)`); bad = 1; } else console.log(`ok: 絵 ${names.length} 個`);
for (const n of names) {
  const [label, svg] = I[n] || [];
  if (!/^[a-z][a-z0-9-]*$/.test(n)) { console.log(`FAIL: 名前「${n}」が英小文字でない`); bad = 1; }
  if (!label || !svg) { console.log(`FAIL: 「${n}」に意味か絵が無い`); bad = 1; continue; }
  if (/#[0-9a-fA-F]{3,8}\b|rgb\(|(fill|stroke)="(?!none)/.test(svg)) { console.log(`FAIL: 「${n}」が色を直接書いている(クラス f-* / ol / ln で塗る)`); bad = 1; }
  if (/<svg|<text|<image|url\(/.test(svg)) { console.log(`FAIL: 「${n}」に使えない要素(svg の入れ子・文字・画像・外部参照)`); bad = 1; }
}
process.exit(bad);' "$SK/engine/icons.js" || fail=1
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
log="$(node "$SK/engine/render-video.mjs" "$SK/references/icon-catalog/index.html" --stills 1 --stills-dir "$OUT" 2>&1)"; code=$?
echo "$log"
echo "$log" | grep -q "Chrome / Edge / Chromium が見つかりません" && { echo "SKIP: Chrome / Edge が見つからない"; exit 3; }
if [ $code -eq 0 ] && [ -f "$OUT/still-1.png" ]; then
  echo "ok: 絵の一覧を撮れた(ページのエラー無し)"
  size=$(wc -c < "$OUT/still-1.png" | tr -d ' ')
  [ "$size" -gt 150000 ] && echo "ok: 一覧の画像 $size バイト" || { echo "FAIL: 一覧の画像が小さすぎる($size バイト = 絵が描けていない疑い)"; fail=1; }
else echo "FAIL: 絵の一覧を撮れない(exit $code)"; fail=1; fi
# はみ出しの「注意」: 上下中央の箱で、上へのはみ出しも拾う / 改行入りの収まる箱は拾わない(PIT-EV-FIT-001)
T="$SK/examples/.test-fit-$$"; mkdir -p "$T"; trap 'rm -rf "$OUT" "$T"' EXIT
cp "$SK/examples/mcp/index.html" "$T/index.html"
cat > "$T/scene.js" <<'JS'
window.VIDEO = {
  items: [
    { id: 'tight', x: 100, y: 100, w: 320, h: 208, icon: 'people', iconAt: 'top', iconSize: 84, html: '<div class="eb">女手</div><div class="k">官女 2000 人</div><div class="d">後宮で働く女性たち</div>' },
    { id: 'roomy', x: 600, y: 100, w: 360, h: 200, icon: 'doc', html: '<div class="k">収まる</div><div class="d">1 行目<br>2 行目</div>' },
  ],
  scenes: [{ dur: 2, pose: 'smile', caption: 'はみ出しの検出', cam: [960, 432, 1], at: [[.2, 'show', 'tight'], [.2, 'show', 'roomy']] }],
};
JS
log2="$(node "$SK/engine/render-video.mjs" "$T/index.html" --stills 1 --stills-dir "$OUT/fit" 2>&1)"
echo "$log2" | grep -q '箱「tight」' && echo "ok: 低すぎる箱に「注意」" || { echo "FAIL: 低すぎる箱(上下中央)のはみ出しを拾わない"; fail=1; }
echo "$log2" | grep -q '箱「roomy」' && { echo "FAIL: 収まる箱(改行あり)に「注意」が出た"; fail=1; } || echo "ok: 収まる箱には出ない"
[ $fail -eq 0 ] && echo "PASS: explainer-icons" || echo "FAIL: explainer-icons"
exit $fail

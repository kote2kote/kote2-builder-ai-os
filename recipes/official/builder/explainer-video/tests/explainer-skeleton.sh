#!/usr/bin/env bash
# TEST-001: 説明映像スキルの部品がそろっているか(cwd = ビルダー直下 or 生成プロジェクトのルート)
# exit 0 = PASS / 1 = FAIL
set -u
SK="${EXPLAINER_DIR:-.claude/skills/explainer-video}"
fail=0
ng() { echo "FAIL: $*"; fail=1; }
ok() { echo "ok: $*"; }

[ -d "$SK" ] || { echo "FAIL: $SK がありません(拡張レシピ explainer-video の Phase 1 が未実行)"; exit 1; }
for f in SKILL.md engine/explainer.js engine/explainer.css engine/render-video.mjs engine/icons.js character/character.js character/TERMS.md \
         references/scene-format.md references/icon-catalog/index.html references/icon-catalog/scene.js \
         examples/mcp/index.html examples/mcp/scene.js examples/mcp/evidence.md examples/mcp/plan.md; do
  [ -f "$SK/$f" ] && ok "$f" || ng "$f がありません"
done

# SKILL.md は 1 行目から YAML frontmatter(無いと Claude Code が登録せず永久に発火しない)
[ "$(head -n 1 "$SK/SKILL.md")" = "---" ] && ok "SKILL.md の先頭が frontmatter" || ng "SKILL.md の 1 行目が --- ではない"
grep -q '^name: explainer-video$' "$SK/SKILL.md" && ok "name" || ng "SKILL.md に name: explainer-video が無い"
grep -q '^description: ' "$SK/SKILL.md" && ok "description" || ng "SKILL.md に description が無い"

# character.js の表にある画像が全部ある
missing=$(grep -oE "'[^']+\.png'" "$SK/character/character.js" | tr -d "'" | while read -r p; do [ -f "$SK/character/$p" ] || echo "$p"; done)
n=$(grep -oE "'[^']+\.png'" "$SK/character/character.js" | wc -l | tr -d ' ')
[ -z "$missing" ] && [ "$n" -ge 1 ] && ok "キャラ画像 $n 枚" || ng "character.js の画像が足りない: $missing"

# ネット無しで動く(エンジン・キャラ・例が外部の URL を読まない)
if grep -nE "(src|href)=[\"']https?://|import .* from [\"']https?://|fetch\(" "$SK/engine/explainer.js" "$SK/engine/explainer.css" "$SK/engine/icons.js" "$SK/character/character.js" "$SK/examples/mcp/index.html" >/dev/null; then
  ng "外部 URL の読み込みがある(オフラインで再生できない)"
else ok "外部の読み込み無し"; fi

# 例と絵の一覧の index.html の読み込み先が実在する(例は絵 = engine/icons.js も読む)
for d in examples/mcp references/icon-catalog; do
  for ref in $(grep -oE '(src|href)="[^"]+"' "$SK/$d/index.html" | sed -E 's/^(src|href)="//; s/"$//'); do
    [ -f "$SK/$d/$ref" ] && ok "$d の読み込み先 $ref" || ng "$d の読み込み先 $ref が無い"
  done
done
grep -q 'engine/icons.js' "$SK/examples/mcp/index.html" && ok "例が絵(icons.js)を読む" || ng "examples/mcp/index.html が engine/icons.js を読んでいない"

[ $fail -eq 0 ] && echo "PASS: explainer-skeleton" || echo "FAIL: explainer-skeleton"
exit $fail

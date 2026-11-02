#!/usr/bin/env bash
# TEST-006: 生成プロジェクトへ正しく写せたか(cwd = ビルダー直下)。
#   bash recipe-tests/explainer-project.sh output/{name}
# 引数が無い / output/{name} にスキルが無い(= 頼まれていない)なら exit 3 = SKIP
set -u
P="${1:-}"
SK=".claude/skills/explainer-video"
[ -n "$P" ] || { echo "SKIP: 対象プロジェクトの指定なし(例: bash recipe-tests/explainer-project.sh output/my-app)"; exit 3; }
[ -d "$P/$SK" ] || { echo "SKIP: $P に説明映像スキルが無い(入れるのは頼まれた時だけ)"; exit 3; }
fail=0
ng() { echo "FAIL: $*"; fail=1; }
# ビルダー直下の正本と同じ中身(差し替え済みの character/ は除く)
for f in SKILL.md engine/explainer.js engine/explainer.css engine/render-video.mjs references/scene-format.md character/TERMS.md examples/mcp/scene.js examples/mcp/index.html; do
  cmp -s "$SK/$f" "$P/$SK/$f" && echo "ok: $f が正本と同じ" || ng "$f が正本と違う / 無い"
done
grep -q 'explainer-video' "$P/CLAUDE.md" && echo "ok: CLAUDE.md の「できること」に 1 行" || ng "$P/CLAUDE.md に explainer-video の 1 行が無い"
if [ -f "$P/.codex/config.toml" ]; then
  A="$P/.agents/skills/explainer-video/SKILL.md"
  [ -f "$A" ] && grep -q 'canonical=.claude/skills/explainer-video/SKILL.md' "$A" && echo "ok: Codex アダプター" || ng "Codex 両対応なのに $A の薄いアダプターが無い"
  d1="$(grep '^description: ' "$SK/SKILL.md")"; d2="$(grep '^description: ' "$A" 2>/dev/null)"
  [ "$d1" = "$d2" ] && echo "ok: description が一字一句同じ" || ng "アダプターの description が正本と違う"
  grep -q '.agents/skills/explainer-video/SKILL.md' "$P/AGENTS.md" && echo "ok: AGENTS.md の対応表" || ng "AGENTS.md の対応表に explainer-video が無い"
  if [ -f "$P/scripts/check-sync.sh" ]; then
    (cd "$P" && bash scripts/check-sync.sh >/dev/null 2>&1) && echo "ok: check-sync 0 FAIL" || ng "check-sync.sh が FAIL"
  fi
fi
[ $fail -eq 0 ] && echo "PASS: explainer-project" || echo "FAIL: explainer-project"
exit $fail

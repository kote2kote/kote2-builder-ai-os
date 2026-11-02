#!/usr/bin/env bash
# TEST-002: 同梱の例(MCP とは)を静止画で撮れるか。Chrome / Edge が無ければ exit 3 = SKIP
set -u
SK="${EXPLAINER_DIR:-.claude/skills/explainer-video}"
command -v node >/dev/null || { echo "FAIL: node がありません(Node.js 18 以上が必要)"; exit 1; }
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
log="$(node "$SK/engine/render-video.mjs" "$SK/examples/mcp/index.html" --stills 2,25,52 --stills-dir "$OUT" 2>&1)"; code=$?
echo "$log"
if [ $code -ne 0 ]; then
  echo "$log" | grep -q "Chrome / Edge / Chromium が見つかりません" && { echo "SKIP: Chrome / Edge が見つからない"; exit 3; }
  echo "FAIL: explainer-stills(exit $code)"; exit 1
fi
# 3 枚とも 1920×1080 の PNG
node -e '
const fs = require("fs"), path = require("path"); let bad = 0;
for (const t of ["2", "25", "52"]) {
  const f = path.join(process.argv[1], `still-${t}.png`);
  if (!fs.existsSync(f)) { console.log("FAIL: " + f + " が無い"); bad = 1; continue; }
  const b = fs.readFileSync(f);
  const w = b.readUInt32BE(16), h = b.readUInt32BE(20);
  if (b.toString("ascii", 1, 4) !== "PNG" || w !== 1920 || h !== 1080) { console.log(`FAIL: still-${t}.png が ${w}x${h}`); bad = 1; }
  else if (b.length < 100000) { console.log(`FAIL: still-${t}.png が小さすぎる(${b.length} バイト = 真っ白の疑い)`); bad = 1; }
  else console.log(`ok: still-${t}.png ${w}x${h} ${b.length} バイト`);
}
process.exit(bad);' "$OUT" || { echo "FAIL: explainer-stills"; exit 1; }
echo "PASS: explainer-stills"

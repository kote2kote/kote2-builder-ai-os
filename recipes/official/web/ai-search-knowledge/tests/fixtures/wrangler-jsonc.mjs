#!/usr/bin/env node
// wrangler-jsonc.mjs — TEST-022 用の wrangler.jsonc 操作(テスト側の独立実装。setup-cloudflare.sh の中のヘルパーとは別に書く)
//   node wrangler-jsonc.mjs name <file>                    → name を 1 行で出す
//   node wrangler-jsonc.mjs kv-id <file>                   → kv_namespaces の binding "REGISTRY" の id を 1 行で出す(無ければ空行)
//   node wrangler-jsonc.mjs reset-id <file>                → REGISTRY の id をプレースホルダに戻す(その場で書く。形式は保持)
//   node wrangler-jsonc.mjs variant <kind> <in> <out>      → 形式違いの設定を作る(内容は同じ / 一部は負例)
//       multiline   : コメントを落として JSON.stringify(indent 2)の複数行に整形(Codex Round 54 の再現)
//       reorder     : multiline + REGISTRY 要素のキー順を id → binding に入れ替え
//       comments    : multiline + REGISTRY 要素の中に偽物の { "binding": "REGISTRY", "id": ... } を含む行コメント / ブロックコメント + 全体に末尾カンマ
//       no-id       : multiline + REGISTRY 要素から id キーを外す(setup が id を挿入できるか)
//       no-registry : multiline + binding を REGISTRY_X に改名(負例: 作成前に止まるべき)
//       broken      : multiline の末尾 3 文字を落とす(負例: JSONC として壊れている)
import fs from "node:fs";

const [mode, ...args] = process.argv.slice(2);
const fail = (m) => { console.error("wrangler-jsonc: " + m); process.exit(3); };

function stripComments(s) {
  let o = "", i = 0; const n = s.length;
  while (i < n) {
    const c = s[i];
    if (c === '"') { let j = i + 1; while (j < n && s[j] !== '"') { if (s[j] === "\\") j++; j++; } o += s.slice(i, j + 1); i = j + 1; continue; }
    if (c === "/" && s[i + 1] === "/") { let e = s.indexOf("\n", i); if (e < 0) e = n; o += " ".repeat(e - i); i = e; continue; }
    if (c === "/" && s[i + 1] === "*") { let e = s.indexOf("*/", i + 2); e = e < 0 ? n : e + 2; o += s.slice(i, e).replace(/[^\n]/g, " "); i = e; continue; }
    o += c; i++;
  }
  return o;
}
function maskStrings(s) {
  let o = "", i = 0; const n = s.length;
  while (i < n) {
    if (s[i] === '"') { let j = i + 1; while (j < n && s[j] !== '"') { if (s[j] === "\\") j++; j++; } o += '"' + " ".repeat(Math.max(0, j - i - 1)) + '"'; i = j + 1; continue; }
    o += s[i]; i++;
  }
  return o;
}
function parseJsonc(src) {
  const code = stripComments(src), mask = maskStrings(code);
  const drop = new Set(); const re = /,(\s*[}\]])/g; let m;
  while ((m = re.exec(mask))) drop.add(m.index);
  let t = ""; for (let i = 0; i < code.length; i++) if (!drop.has(i)) t += code[i];
  return JSON.parse(t);
}
// REGISTRY 要素の id を差し替える(コメント・整形は保持)。要素が無ければ null
function replaceRegistryId(src, newId) {
  const code = stripComments(src), mask = maskStrings(code);
  const arr = /"kv_namespaces"\s*:\s*\[/.exec(code); if (!arr) return null;
  const arrOpen = arr.index + arr[0].length - 1;
  const close = (open, oc, cc) => { let d = 0; for (let i = open; i < mask.length; i++) { if (mask[i] === oc) d++; else if (mask[i] === cc && --d === 0) return i; } return -1; };
  const arrClose = close(arrOpen, "[", "]");
  const re = /"binding"\s*:\s*"REGISTRY"/g; let m;
  while ((m = re.exec(code))) {
    if (m.index < arrOpen || m.index > arrClose) continue;
    let d = 0, open = -1;
    for (let i = m.index; i > arrOpen; i--) { if (mask[i] === "}") d++; else if (mask[i] === "{") { if (d === 0) { open = i; break; } d--; } }
    if (open < 0) continue;
    const end = close(open, "{", "}");
    const idm = /"id"\s*:\s*"[^"]*"/.exec(code.slice(open, end + 1));
    if (!idm) return null;
    return src.slice(0, open + idm.index) + '"id": "' + newId + '"' + src.slice(open + idm.index + idm[0].length);
  }
  return null;
}

const read = (f) => fs.readFileSync(f, "utf8");
if (mode === "name") {
  const cfg = parseJsonc(read(args[0])); process.stdout.write((cfg.name || "") + "\n");
} else if (mode === "kv-id") {
  const cfg = parseJsonc(read(args[0]));
  const r = Array.isArray(cfg.kv_namespaces) ? cfg.kv_namespaces.find((k) => k && k.binding === "REGISTRY") : null;
  process.stdout.write(((r && r.id) || "") + "\n");
} else if (mode === "reset-id") {
  const next = replaceRegistryId(read(args[0]), "REPLACE_WITH_KV_NAMESPACE_ID");
  if (next == null) fail("REGISTRY の id をリセットできない: " + args[0]);
  fs.writeFileSync(args[0], next);
} else if (mode === "variant") {
  const [kind, inFile, outFile] = args;
  const src = read(inFile);
  const cfg = parseJsonc(src);
  const kv = Array.isArray(cfg.kv_namespaces) ? cfg.kv_namespaces.find((k) => k && k.binding === "REGISTRY") : null;
  if (!kv) fail("入力に REGISTRY が無い");
  const multiline = () => JSON.stringify(cfg, null, 2) + "\n";
  let out;
  if (kind === "multiline") out = multiline();
  else if (kind === "reorder") {
    const { binding, id, ...rest } = kv; const idx = cfg.kv_namespaces.indexOf(kv);
    cfg.kv_namespaces[idx] = { ...rest, id, binding }; out = multiline();
  } else if (kind === "comments") {
    out = multiline().replace(/("kv_namespaces":\s*\[\s*\{)/, '$1\n      // 偽物(コメント): { "binding": "REGISTRY", "id": "0000" } ← ここは読まない\n      /* ブロックコメント { "id": "1111" \n         2 行目 } */');
    out = out.replace(/([^,\s])\n(\s*[}\]])/g, "$1,\n$2");   // 末尾カンマを全部に付ける
  } else if (kind === "no-id") { delete kv.id; out = multiline(); }
  else if (kind === "no-registry") { kv.binding = "REGISTRY_X"; out = multiline(); }
  else if (kind === "broken") { out = multiline().slice(0, -3); }
  else fail("不明な variant: " + kind);
  fs.writeFileSync(outFile, out);
} else fail("mode は name / kv-id / reset-id / variant");

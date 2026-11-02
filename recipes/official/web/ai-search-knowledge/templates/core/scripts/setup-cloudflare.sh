#!/usr/bin/env bash
# setup-cloudflare.sh — Phase 1(レシピ ai-search-knowledge の templates/core 参照実装。コピーして使い、散文から再導出しない): Cloudflare 側のリソース(R2 バケット / KV namespace / AI Search インスタンス)を
# 「1 生成物 = 1 組」で用意する(core レシピ §5 Phase 1 / §6 PIT-MULTIBUILD-001・PIT-SETUP-KV-001 / TEST-022)。
#
# 使い方:
#   bash scripts/setup-cloudflare.sh            # 同名リソースが 1 つでもあれば何も作らず・書き換えずに止まる(exit 1)
#   bash scripts/setup-cloudflare.sh --reuse    # 既存を意図して引き継ぐ時だけ。無いものだけ作り、最後に KV id を書く
#
# 順序は固定(fail-closed。途中で失敗したら以降は何もしない):
#   (a) wrangler.jsonc を字句解析して読む(改行・キー順・コメント・末尾カンマに依存しない)。4 か所(name / vars.INSTANCE_NAME /
#       bucket_name / instance_name)が同じ名前から派生しているか + kv_namespaces の binding "REGISTRY" に id を書ける形か(書込の予行)
#   (b) ログイン確認(wrangler whoami)
#   (c) 3 種すべてを事前照会(R2 一覧 / KV 一覧 / AI Search 一覧)。一覧の取得失敗・解釈失敗は非ゼロ終了 = 「既存なし」に倒さない
#   (d) 同名が 1 つでもあれば止まる(--reuse の時だけ引き継ぐ)
#   (e) 無いものだけ作成(作成失敗は非ゼロ終了)
#   (f) 最後に 1 回だけ KV id を wrangler.jsonc へ書く(コメント・整形は保持。書いた後に読み直して照合)
#
# wrangler は常に `pnpm exec wrangler` で呼ぶ(疑似 CLI で境界テストできるように、pnpm を差し替え可能にしておく)。
set -u

CONFIG="wrangler.jsonc"
REUSE=0
for arg in "$@"; do
  case "$arg" in
    --reuse) REUSE=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "ERROR: 不明な引数: $arg" >&2; exit 2 ;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

[[ -f "$CONFIG" ]] || die "$CONFIG が無い(プロジェクト直下で実行してください)"
[[ -w "$CONFIG" ]] || die "$CONFIG に書き込めない(権限を確認してください)"
command -v pnpm >/dev/null 2>&1 || die "pnpm が無い(README の手順でインストールしてください)"
command -v node >/dev/null 2>&1 || die "node が無い(README の手順でインストールしてください)"

# ---------- JSONC ヘルパー(node。設定の改行・キー順・コメント・末尾カンマに依存しない) ----------
#   read  <file>              → 5 行(name / vars.INSTANCE_NAME / r2_buckets[0].bucket_name / ai_search[0].instance_name / REGISTRY の id)。読めなければ exit 3
#   patch <file> <id> <out>   → kv_namespaces の binding "REGISTRY" の id だけ差し替えた本文を out(- は stdout)へ。コメント・整形は保持。書けなければ exit 3
JSONC_TOOL='
const fs = require("fs");
const [mode, file, a3, a4] = process.argv.slice(1);
const fail = (m) => { console.error("JSONC: " + m); process.exit(3); };
const src = fs.readFileSync(file, "utf8");
// コメントだけを空白に置き換える(長さ・改行位置は不変。文字列の中は触らない)
function blankComments(s) {
  let o = "", i = 0; const n = s.length;
  while (i < n) {
    const c = s[i];
    if (c === "\"") { let j = i + 1; while (j < n && s[j] !== "\"") { if (s[j] === "\\") j++; j++; } o += s.slice(i, j + 1); i = j + 1; continue; }
    if (c === "/" && s[i + 1] === "/") { let e = s.indexOf("\n", i); if (e < 0) e = n; o += " ".repeat(e - i); i = e; continue; }
    if (c === "/" && s[i + 1] === "*") { let e = s.indexOf("*/", i + 2); e = e < 0 ? n : e + 2; o += s.slice(i, e).replace(/[^\n]/g, " "); i = e; continue; }
    o += c; i++;
  }
  return o;
}
// 文字列の中身も空白にする(構造探索用。引用符と長さは保つ)
function maskStrings(s) {
  let o = "", i = 0; const n = s.length;
  while (i < n) {
    if (s[i] === "\"") { let j = i + 1; while (j < n && s[j] !== "\"") { if (s[j] === "\\") j++; j++; } o += "\"" + " ".repeat(Math.max(0, j - i - 1)) + "\""; i = j + 1; continue; }
    o += s[i]; i++;
  }
  return o;
}
const code = blankComments(src);
const mask = maskStrings(code);
// 末尾カンマ(構造上の位置だけ)を落として JSON として解釈する
function parse() {
  const drop = new Set(); const re = /,(\s*[}\]])/g; let m;
  while ((m = re.exec(mask))) drop.add(m.index);
  let t = ""; for (let i = 0; i < code.length; i++) if (!drop.has(i)) t += code[i];
  try { return JSON.parse(t); } catch (e) { fail(file + " を JSONC として解釈できない: " + e.message); }
}
// kv_namespaces 配列の中の binding "REGISTRY" 要素の範囲 [open, close] を返す(コメント・文字列の偽物は無視)
function registryObject() {
  const arr = /"kv_namespaces"\s*:\s*\[/.exec(code);
  if (!arr) fail("kv_namespaces が無い");
  const arrOpen = arr.index + arr[0].length - 1;
  const arrClose = matchClose(arrOpen, "[", "]");
  const re = /"binding"\s*:\s*"REGISTRY"/g; let m;
  while ((m = re.exec(code))) {
    if (m.index < arrOpen || m.index > arrClose) continue;
    let d = 0, open = -1;
    for (let i = m.index; i > arrOpen; i--) { if (mask[i] === "}") d++; else if (mask[i] === "{") { if (d === 0) { open = i; break; } d--; } }
    if (open < 0) continue;
    return { open, close: matchClose(open, "{", "}"), bindEnd: m.index + m[0].length };
  }
  fail("kv_namespaces に binding \"REGISTRY\" の要素が無い");
}
function matchClose(open, oc, cc) {
  let d = 0;
  for (let i = open; i < mask.length; i++) { if (mask[i] === oc) d++; else if (mask[i] === cc) { d--; if (d === 0) return i; } }
  fail("括弧が閉じていない");
}
const cfg = parse();
const str = (v) => (typeof v === "string" ? v : "");
const reg = Array.isArray(cfg.kv_namespaces) ? cfg.kv_namespaces.find((k) => k && k.binding === "REGISTRY") : null;
if (mode === "read") {
  if (!reg) fail("kv_namespaces に binding \"REGISTRY\" の要素が無い");
  const out = [str(cfg.name), str(cfg.vars && cfg.vars.INSTANCE_NAME),
    str(Array.isArray(cfg.r2_buckets) && cfg.r2_buckets[0] && cfg.r2_buckets[0].bucket_name),
    str(Array.isArray(cfg.ai_search) && cfg.ai_search[0] && cfg.ai_search[0].instance_name), str(reg.id)];
  if (out.some((v) => /[\n\t]/.test(v))) fail("値に改行 / タブが含まれる");
  process.stdout.write(out.join("\n") + "\n");
} else if (mode === "patch") {
  const id = a3, outFile = a4;
  if (!/^[0-9a-f]{32}$/.test(id)) fail("id が 32 桁 16 進でない: " + id);
  const { open, close, bindEnd } = registryObject();
  const seg = code.slice(open, close + 1);
  const idm = /"id"\s*:\s*"[^"]*"/.exec(seg);
  let next;
  if (idm) next = src.slice(0, open + idm.index) + "\"id\": \"" + id + "\"" + src.slice(open + idm.index + idm[0].length);
  else next = src.slice(0, bindEnd) + ", \"id\": \"" + id + "\"" + src.slice(bindEnd);
  // 書いた結果を読み直して照合(壊れた本文を書かない)
  let check; try { check = JSON.parse(blankComments(next).replace(/,(\s*[}\]])/g, "$1")); } catch (e) { fail("書き込み後の本文を解釈できない: " + e.message); }
  const r2 = Array.isArray(check.kv_namespaces) ? check.kv_namespaces.find((k) => k && k.binding === "REGISTRY") : null;
  if (!r2 || r2.id !== id) fail("書き込み後の REGISTRY id が一致しない");
  if (outFile === "-") process.stdout.write(next); else fs.writeFileSync(outFile, next);
} else fail("mode は read / patch");
'
jsonc_tool() { node -e "$JSONC_TOOL" "$@"; }

# ---------- (a) 名前の整合 + 書込の予行 ----------
READ_OUT="$(jsonc_tool read "$CONFIG")" || die "$CONFIG を読めない(JSONC として解釈できない / kv_namespaces に binding \"REGISTRY\" が無い)"
{ read -r NAME; read -r INSTANCE_VAR; read -r BUCKET; read -r INSTANCE; read -r KV_ID_CURRENT; } <<< "$READ_OUT"

[[ -n "$NAME" ]] || die "$CONFIG から name を読めない"
[[ "$INSTANCE_VAR" == "$NAME" ]] || die "名前が不整合: vars.INSTANCE_NAME=\"$INSTANCE_VAR\" は name=\"$NAME\" と同じにする(4 か所を同じ接尾辞で揃える)"
[[ "$BUCKET" == "${NAME}-docs" ]] || die "名前が不整合: bucket_name=\"$BUCKET\" は \"${NAME}-docs\" にする(4 か所を同じ接尾辞で揃える)"
[[ "$INSTANCE" == "$NAME" ]] || die "名前が不整合: ai_search.instance_name=\"$INSTANCE\" は name=\"$NAME\" と同じにする(4 か所を同じ接尾辞で揃える)"
KV_TITLE="${NAME}-REGISTRY"
# 作成前に「最後の書き込み」が通るか予行する(ここで止まればクラウドには何も作らない)
jsonc_tool patch "$CONFIG" "0123456789abcdef0123456789abcdef" - >/dev/null \
  || die "$CONFIG の kv_namespaces(binding \"REGISTRY\")に id を書き込める形でない(作成前に止めました)"
info "名前の整合 OK: name=$NAME / bucket=$BUCKET / instance=$INSTANCE / KV title=$KV_TITLE"

# ---------- (b) ログイン確認 ----------
WHOAMI="$(pnpm exec wrangler whoami 2>&1)" || die "wrangler にログインしていない(pnpm exec wrangler login を先に)"
echo "$WHOAMI" | grep -qiE 'account|logged in|you are' || die "wrangler whoami の出力を解釈できない(ログイン状態を確認してください)"
info "ログイン OK"

# ---------- (c) 3 種の事前照会(解釈失敗は「既存なし」に倒さない) ----------
# R2: テキスト出力。「Listing buckets」見出しも name: 行も無ければ想定外 → 失敗。見出しだけなら空一覧
R2_OUT="$(pnpm exec wrangler r2 bucket list 2>&1)" || die "R2 バケット一覧の取得に失敗: $(echo "$R2_OUT" | tail -n 3)"
if ! echo "$R2_OUT" | grep -qiE 'Listing buckets|^[[:space:]]*name:'; then
  die "R2 バケット一覧の出力を解釈できない(見出しも name: 行も無い)。出力: $(echo "$R2_OUT" | head -n 3)"
fi
R2_EXISTS=0
echo "$R2_OUT" | grep -E '^[[:space:]]*name:[[:space:]]*'"$BUCKET"'[[:space:]]*$' >/dev/null && R2_EXISTS=1

# KV: JSON 配列。配列でない / 同名 title の要素に 32 桁 16 進の id が無い → 失敗
KV_OUT="$(pnpm exec wrangler kv namespace list 2>/dev/null)" || die "KV namespace 一覧の取得に失敗"
KV_JSON="$(echo "$KV_OUT" | sed -n '/^[[:space:]]*\[/,$p')"
KV_PARSE="$(KV_JSON="$KV_JSON" KV_TITLE="$KV_TITLE" node -e '
  let list; try { list = JSON.parse(process.env.KV_JSON); } catch { console.log("PARSE_ERROR"); process.exit(0); }
  if (!Array.isArray(list)) { console.log("NOT_ARRAY"); process.exit(0); }
  const hit = list.find((n) => n && n.title === process.env.KV_TITLE);
  if (!hit) { console.log("NONE"); process.exit(0); }
  if (typeof hit.id !== "string" || !/^[0-9a-f]{32}$/.test(hit.id)) { console.log("BAD_ID"); process.exit(0); }
  console.log(hit.id);
' 2>/dev/null)" || die "KV 一覧の解釈に失敗(node が必要)"
case "$KV_PARSE" in
  PARSE_ERROR|NOT_ARRAY|"") die "KV namespace 一覧の出力を解釈できない(JSON 配列でない)" ;;
  BAD_ID) die "KV namespace \"$KV_TITLE\" は一覧にあるが id が 32 桁 16 進でない(出力の形が想定外)" ;;
  NONE) KV_EXISTS=0; KV_ID="" ;;
  *) KV_EXISTS=1; KV_ID="$KV_PARSE" ;;
esac

# AI Search: --json の配列。配列でない → 失敗
AIS_OUT="$(pnpm exec wrangler ai-search list --json 2>/dev/null)" || die "AI Search インスタンス一覧の取得に失敗"
AIS_JSON="$(echo "$AIS_OUT" | sed -n '/^[[:space:]]*\[/,$p')"
AIS_PARSE="$(AIS_JSON="$AIS_JSON" INSTANCE="$INSTANCE" node -e '
  let list; try { list = JSON.parse(process.env.AIS_JSON); } catch { console.log("PARSE_ERROR"); process.exit(0); }
  if (!Array.isArray(list)) { console.log("NOT_ARRAY"); process.exit(0); }
  const hit = list.some((i) => i && (i.name === process.env.INSTANCE || i.id === process.env.INSTANCE));
  console.log(hit ? "EXISTS" : "NONE");
' 2>/dev/null)" || die "AI Search 一覧の解釈に失敗(node が必要)"
case "$AIS_PARSE" in
  EXISTS) AIS_EXISTS=1 ;;
  NONE) AIS_EXISTS=0 ;;
  *) die "AI Search インスタンス一覧の出力を解釈できない(JSON 配列でない)" ;;
esac
info "事前照会 OK: R2=$([[ $R2_EXISTS == 1 ]] && echo あり || echo なし) / KV=$([[ $KV_EXISTS == 1 ]] && echo あり || echo なし) / AI Search=$([[ $AIS_EXISTS == 1 ]] && echo あり || echo なし)"

# ---------- (d) 同名があれば止まる(--reuse の時だけ引き継ぐ) ----------
if (( R2_EXISTS + KV_EXISTS + AIS_EXISTS > 0 )) && (( REUSE == 0 )); then
  cat >&2 <<EOF
ERROR: 同名のリソースが既にあります(何も作成せず、$CONFIG も書き換えていません)。
  R2 バケット \"$BUCKET\": $([[ $R2_EXISTS == 1 ]] && echo 既存 || echo なし)
  KV namespace \"$KV_TITLE\": $([[ $KV_EXISTS == 1 ]] && echo 既存 || echo なし)
  AI Search \"$INSTANCE\": $([[ $AIS_EXISTS == 1 ]] && echo 既存 || echo なし)
1 生成物 = 1 組の保管庫にするのが規約です(別の生成物と共有すると台帳・サムネイル・キーの形式がずれます = PIT-MULTIBUILD-001)。
  - 別物として建てるなら: $CONFIG の 4 か所(name / vars.INSTANCE_NAME / bucket_name / instance_name)を同じ接尾辞(例 -2)で揃えて再実行
  - このリソースを意図して引き継ぐなら: bash scripts/setup-cloudflare.sh --reuse
EOF
  exit 1
fi

# ---------- (e) 無いものだけ作成(失敗は非ゼロ終了) ----------
if (( R2_EXISTS == 0 )); then
  info "R2 バケットを作成: $BUCKET"
  pnpm exec wrangler r2 bucket create "$BUCKET" || die "R2 バケットの作成に失敗: $BUCKET"
else
  info "R2 バケットは既存を引き継ぐ: $BUCKET"
fi

if (( KV_EXISTS == 0 )); then
  info "KV namespace を作成: $KV_TITLE"
  KV_CREATE_OUT="$(pnpm exec wrangler kv namespace create "$KV_TITLE" 2>&1)" || die "KV namespace の作成に失敗: $KV_TITLE"
  KV_ID="$(echo "$KV_CREATE_OUT" | grep -oE '"?id"?[[:space:]]*[:=][[:space:]]*"?[0-9a-f]{32}"?' | grep -oE '[0-9a-f]{32}' | head -n 1)"
  [[ -n "$KV_ID" ]] || die "作成した KV namespace の id を読み取れない(出力: $(echo "$KV_CREATE_OUT" | tail -n 3))"
else
  info "KV namespace は既存を引き継ぐ: $KV_TITLE ($KV_ID)"
fi

if (( AIS_EXISTS == 0 )); then
  info "AI Search インスタンスを作成: $INSTANCE(source: $BUCKET / hybrid-search 有効)"
  pnpm exec wrangler ai-search create "$INSTANCE" --type r2 --source "$BUCKET" --hybrid-search true \
    || die "AI Search インスタンスの作成に失敗: $INSTANCE"
  info "初回の同期ジョブを起動"
  pnpm exec wrangler ai-search jobs create "$INSTANCE" || echo "WARN: 初回同期ジョブの起動に失敗(後で pnpm exec wrangler ai-search jobs create $INSTANCE を実行)"
else
  info "AI Search インスタンスは既存を引き継ぐ: $INSTANCE"
fi

# ---------- (f) 最後に 1 回だけ KV id を書く(コメント・整形は保持) ----------
[[ "$KV_ID" =~ ^[0-9a-f]{32}$ ]] || die "KV id が不正: '$KV_ID'"
TMP="$(mktemp)"
jsonc_tool patch "$CONFIG" "$KV_ID" "$TMP" || { rm -f "$TMP"; die "$CONFIG への KV id 書き込みに失敗(kv_namespaces の REGISTRY 要素に id を書けない)"; }
mv "$TMP" "$CONFIG"
{ read -r _; read -r _; read -r _; read -r _; read -r KV_ID_WRITTEN; } <<< "$(jsonc_tool read "$CONFIG")"
[[ "$KV_ID_WRITTEN" == "$KV_ID" ]] || die "$CONFIG を読み直したら KV id が一致しない(書き込み結果を確認してください)"
info "KV id を $CONFIG に書き込みました($KV_ID_CURRENT → $KV_ID)"

cat <<EOF

セットアップ完了。次の一歩:
  1. cp .env.example .env && cp .env .dev.vars  (ADMIN_TOKEN などを埋める。同期トークンは後回しでも動く)
  2. pnpm dev   (= wrangler dev --remote。起動ログの Ready on の URL をブラウザで開く)
EOF

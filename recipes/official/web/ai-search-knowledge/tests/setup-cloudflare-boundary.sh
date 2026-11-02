#!/usr/bin/env bash
# setup-cloudflare-boundary.sh — TEST-022: scripts/setup-cloudflare.sh の境界テスト(疑似 wrangler・クラウド不要)
# 使い方: bash recipe-tests/setup-cloudflare-boundary.sh   (cwd = 生成プロジェクト直下)
# 見るもの: exit code / wrangler.jsonc が書き換わったか / どの作成コマンドを呼んだか / 作成 KV の title / 書かれた KV id
#           + 設定の形式(複数行・キー順・コメント・末尾カンマ)に依存せず建つか / 形式の負例では作成前に止まるか
set -u
ROOT="$(pwd)"
[[ -f "$ROOT/scripts/setup-cloudflare.sh" && -f "$ROOT/wrangler.jsonc" ]] || { echo "[FAIL] scripts/setup-cloudflare.sh か wrangler.jsonc が無い(生成プロジェクト直下で実行する)"; exit 1; }
FAKE="$ROOT/recipe-tests/fixtures/fake-pnpm.sh"
JSONC="$ROOT/recipe-tests/fixtures/wrangler-jsonc.mjs"
[[ -f "$FAKE" ]] || { echo "[FAIL] recipe-tests/fixtures/fake-pnpm.sh が無い"; exit 1; }
[[ -f "$JSONC" ]] || { echo "[FAIL] recipe-tests/fixtures/wrangler-jsonc.mjs が無い"; exit 1; }
NAME="$(node "$JSONC" name "$ROOT/wrangler.jsonc" 2>/dev/null)"
[[ -n "$NAME" ]] || { echo "[FAIL] wrangler.jsonc の name が読めない"; exit 1; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/setup-boundary.XXXXXX")"; trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin"; cp "$FAKE" "$WORK/bin/pnpm"; chmod +x "$WORK/bin/pnpm"
PASS=0; FAIL=0
run_case() { # label exists fail want_exit want_changed want_created [extra-arg] [variant]
  local label="$1" ex="$2" fl="$3" we="$4" wc="$5" wcr="$6" extra="${7:-}" variant="${8:-asis}"
  local T; T="$(mktemp -d "$WORK/case.XXXXXX")"; mkdir -p "$T/scripts" "$T/node_modules/.bin"
  cp "$ROOT/wrangler.jsonc" "$T/"; cp "$ROOT/scripts/setup-cloudflare.sh" "$T/scripts/"
  printf '#!/bin/sh\necho "direct wrangler call" >&2; exit 9\n' > "$T/node_modules/.bin/wrangler"; chmod +x "$T/node_modules/.bin/wrangler"
  # KV id は未設定状態から始める(32 桁 16 進でない値にする。形式に依存しない置換)
  node "$JSONC" reset-id "$T/wrangler.jsonc" || { echo "[FAIL] $label: KV id のリセットに失敗"; FAIL=$((FAIL+1)); return; }
  # 設定の形式違い(内容は同じ / stop-* は負例)
  case "$variant" in
    asis) ;;
    stop-*) node "$JSONC" variant "${variant#stop-}" "$T/wrangler.jsonc" "$T/wrangler.jsonc" || { echo "[FAIL] $label: variant 生成失敗"; FAIL=$((FAIL+1)); return; } ;;
    *)      node "$JSONC" variant "$variant" "$T/wrangler.jsonc" "$T/wrangler.jsonc" || { echo "[FAIL] $label: variant 生成失敗"; FAIL=$((FAIL+1)); return; } ;;
  esac
  local before after rc changed created ok=1
  before="$(cksum "$T/wrangler.jsonc")"; : > "$T/log"
  ( cd "$T" && FAKE_NAME="$NAME" FAKE_EXISTS="$ex" FAKE_FAIL="$fl" FAKE_LOG="$T/log" PATH="$WORK/bin:$PATH" bash scripts/setup-cloudflare.sh $extra > "$T/out" 2>&1 ); rc=$?
  after="$(cksum "$T/wrangler.jsonc")"; changed=0; [[ "$before" != "$after" ]] && changed=1
  created="$(grep -oE '^create-[a-z0-9]+' "$T/log" | tr '\n' ' ' | sed 's/ $//')"
  [[ $rc -eq $we && $changed -eq $wc && "$created" == "$wcr" ]] || ok=0
  if [[ $ok -eq 1 && "$wcr" == *create-kv* ]]; then  # 作成 KV の title は {name}-REGISTRY(PIT-SETUP-KV-001)
    grep -qxF "create-kv ${NAME}-REGISTRY" "$T/log" || { ok=0; echo "       KV の title が ${NAME}-REGISTRY でない: $(grep '^create-kv' "$T/log")"; }
  fi
  if [[ $ok -eq 1 && "$variant" == stop-* && -s "$T/log" ]]; then  # 形式の負例は CLI を 1 回も呼ばずに止まる
    ok=0; echo "       作成前に止まるべきなのに CLI を呼んだ: $(tr '\n' ' ' < "$T/log")"
  fi
  if [[ $ok -eq 1 && $wc -eq 1 ]]; then  # 書かれた id が 32 桁 16 進で読み戻せる(形式を壊していない)
    local written; written="$(node "$JSONC" kv-id "$T/wrangler.jsonc" 2>/dev/null)"
    [[ "$written" =~ ^[0-9a-f]{32}$ ]] || { ok=0; echo "       書き込み後の REGISTRY id を読み戻せない: '$written'"; }
    if [[ "$variant" == "comments" ]] && ! grep -q '偽物(コメント)' "$T/wrangler.jsonc"; then ok=0; echo "       書き込みでコメントが消えた"; fi
  fi
  if [[ $ok -eq 1 ]]; then echo "[ok]   $label"; PASS=$((PASS+1)); else echo "[FAIL] $label: exit $rc(期待 $we)/ 設定変更 $changed(期待 $wc)/ 作成 '${created}'(期待 '$wcr')"; tail -n 6 "$T/out" | sed 's/^/       /'; FAIL=$((FAIL+1)); fi
}
run_case "新規(重複なし)"                 ""         ""            0 1 "create-r2 create-kv create-ai"
run_case "R2 が空のアカウント"             ""         "r2-empty"    0 1 "create-r2 create-kv create-ai"
run_case "R2 だけ既存"                     "r2"       ""            1 0 ""
run_case "KV だけ既存"                     "kv"       ""            1 0 ""
run_case "インスタンスだけ既存"             "ai"       ""            1 0 ""
run_case "3 つとも既存"                    "r2,kv,ai" ""            1 0 ""
run_case "インスタンス既存 + --reuse"       "ai"       ""            0 1 "create-r2 create-kv" "--reuse"
run_case "3 つとも既存 + --reuse"          "r2,kv,ai" ""            0 1 ""                    "--reuse"
run_case "R2 一覧の取得失敗"               ""         "list-r2"     1 0 ""
run_case "KV 一覧の取得失敗"               ""         "list-kv"     1 0 ""
run_case "AI Search 一覧の取得失敗"        ""         "list-ai"     1 0 ""
run_case "KV 一覧が JSON でない"           ""         "badjson"     1 0 ""
run_case "R2 一覧が想定外の形"             ""         "r2-unknown"  1 0 ""
run_case "同名 KV の要素に id が無い"      ""         "kv-noid-list" 1 0 ""
run_case "R2 作成失敗"                     ""         "create-r2"   1 0 "create-r2"
run_case "KV 作成失敗"                     ""         "create-kv"   1 0 "create-r2 create-kv"
run_case "KV 作成後に id を読めない"        ""         "kv-noid"     1 0 "create-r2 create-kv"
run_case "AI Search 作成失敗"              ""         "create-ai"   1 0 "create-r2 create-kv create-ai"
run_case "不明な引数"                      ""         ""            2 0 ""                    "--bogus"
# 設定の形式に依存しない(内容は同じ。Codex Round 54: 複数行に整形しただけで id を書けず止まっていた)
run_case "形式: 複数行 JSON(新規)"          ""         ""            0 1 "create-r2 create-kv create-ai" "" "multiline"
run_case "形式: 複数行 + 3 つとも既存"      "r2,kv,ai" ""            1 0 ""                    ""        "multiline"
run_case "形式: 複数行 + --reuse"           "r2,kv,ai" ""            0 1 ""                    "--reuse" "multiline"
run_case "形式: id が binding より前"       ""         ""            0 1 "create-r2 create-kv create-ai" "" "reorder"
run_case "形式: 偽物コメント + 末尾カンマ"  ""         ""            0 1 "create-r2 create-kv create-ai" "" "comments"
run_case "形式: REGISTRY に id キーが無い"  ""         ""            0 1 "create-r2 create-kv create-ai" "" "no-id"
# 形式の負例: 設定を解釈できない / 書けない → CLI を呼ばず・作らず・書き換えずに止まる
run_case "形式: binding REGISTRY が無い"    ""         ""            1 0 ""                    ""        "stop-no-registry"
run_case "形式: JSONC として壊れている"     ""         ""            1 0 ""                    ""        "stop-broken"
# name だけ改名(他 3 か所が不整合)→ CLI を呼ばずに止まる
T="$(mktemp -d "$WORK/mm.XXXXXX")"; mkdir -p "$T/scripts" "$T/node_modules/.bin"; cp "$ROOT/scripts/setup-cloudflare.sh" "$T/scripts/"; printf '#!/bin/sh\nexit 9\n' > "$T/node_modules/.bin/wrangler"; chmod +x "$T/node_modules/.bin/wrangler"
node -e 'const fs=require("fs");let s=fs.readFileSync(process.argv[1],"utf8");s=s.replace(/("name"\s*:\s*")([^"]+)(")/,"$1$2-renamed$3");fs.writeFileSync(process.argv[2],s)' "$ROOT/wrangler.jsonc" "$T/wrangler.jsonc"; : > "$T/log"
( cd "$T" && FAKE_NAME="$NAME" FAKE_LOG="$T/log" PATH="$WORK/bin:$PATH" bash scripts/setup-cloudflare.sh > "$T/out" 2>&1 ); rc=$?
if [[ $rc -eq 1 && ! -s "$T/log" ]]; then echo "[ok]   name だけ改名 → CLI を呼ばず停止"; PASS=$((PASS+1)); else echo "[FAIL] name だけ改名: exit $rc / CLI 呼び出し: $(tr '\n' ' ' < "$T/log")"; FAIL=$((FAIL+1)); fi
echo "setup-cloudflare boundary: PASS=$PASS / FAIL=$FAIL"
[[ $FAIL -eq 0 ]]

#!/usr/bin/env bash
# TEST-019 / CORE-02: 根拠表示用のページ画像が横幅 1980px で生成されている(§5 Phase 4。拡大表示に耐える解像度)
#
# 使い方:
#   bash recipe-tests/evidence-image-width-1980.sh <画像ファイル>        ← PNG / JPEG のどちらでも可(ヘッダだけ読む・外部依存なし)
#   bash recipe-tests/evidence-image-width-1980.sh                       ← 引数なし: $EVIDENCE_IMAGE → recipe-tests/evidence/* の順に探す
# 画像の取り方(dev 起動中): curl -s -o recipe-tests/evidence/page1.jpg "http://localhost:8787/api/kb/{kb}/docs/{doc}/thumb/1"
#   ({kb} / {doc} は画面の資料一覧 or GET /api/kb/{kb}/docs で分かる。登録済み PDF の 1 ページ目で十分)
#
# 判定: 幅が 1980 ± 2 px なら PASS(exit 0)。それ以外は FAIL(exit 1)。
# ★検査する画像が 1 枚も無い時は "SKIP:" を表示して exit 0 で終わる(auto 行を止めないための仕様。PASS の証拠にはならないので、
#   report では SKIP として扱うこと)。
set -u
EXPECT=1980
TOL=2

pick_file() {
  if [[ $# -ge 1 && -n "${1:-}" ]]; then echo "$1"; return; fi
  if [[ -n "${EVIDENCE_IMAGE:-}" ]]; then echo "$EVIDENCE_IMAGE"; return; fi
  local f
  for f in recipe-tests/evidence/*.png recipe-tests/evidence/*.jpg recipe-tests/evidence/*.jpeg; do
    [[ -f "$f" ]] && { echo "$f"; return; }
  done
  echo ""
}

FILE="$(pick_file "$@")"
if [[ -z "$FILE" ]]; then
  echo "SKIP: 検査する根拠画像がありません(引数・EVIDENCE_IMAGE・recipe-tests/evidence/*.{png,jpg} のいずれかで指定。取り方は本スクリプト冒頭)"
  exit 0
fi
if [[ ! -f "$FILE" ]]; then
  echo "FAIL: ファイルが無い: $FILE"; exit 1
fi

# --- 幅の読み取り(python3 があればそれで、無ければ od + awk。どちらも標準装備の範囲) ---
read_width_python() {
  python3 - "$FILE" <<'PY'
import struct, sys
p = sys.argv[1]
with open(p, "rb") as f:
    data = f.read(4 * 1024 * 1024)
if data[:8] == b"\x89PNG\r\n\x1a\n":
    print(struct.unpack(">I", data[16:20])[0]); sys.exit(0)
if data[:2] == b"\xff\xd8":
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF: i += 1; continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7: i += 2; continue
        seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            print(struct.unpack(">H", data[i + 7:i + 9])[0]); sys.exit(0)
        i += 2 + seglen
    print("ERR:JPEG SOF が見つからない"); sys.exit(0)
print("ERR:PNG / JPEG ではない")
PY
}

read_width_od() {
  # od でバイト列を 10 進で並べ、awk でヘッダを歩く
  od -An -v -tu1 -N 4194304 "$FILE" | tr -s ' \n' ' ' | awk '
  {
    n = split($0, b, " ");
    if (b[1]==137 && b[2]==80 && b[3]==78 && b[4]==71) { print b[17]*16777216 + b[18]*65536 + b[19]*256 + b[20]; exit }
    if (b[1]==255 && b[2]==216) {
      i = 3;
      while (i + 9 <= n) {
        if (b[i] != 255) { i++; continue }
        m = b[i+1];
        if (m==216 || m==1 || (m>=208 && m<=215)) { i += 2; continue }
        seglen = b[i+2]*256 + b[i+3];
        if (m==192||m==193||m==194||m==195||m==197||m==198||m==199||m==201||m==202||m==203||m==205||m==206||m==207) { print b[i+7]*256 + b[i+8]; exit }
        i += 2 + seglen;
      }
      print "ERR:JPEG SOF が見つからない"; exit
    }
    print "ERR:PNG / JPEG ではない"
  }'
}

if command -v python3 >/dev/null 2>&1; then W="$(read_width_python)"; else W="$(read_width_od)"; fi
case "$W" in
  ERR:*) echo "FAIL: $FILE — ${W#ERR:}"; exit 1 ;;
  ''|*[!0-9]*) echo "FAIL: $FILE — 幅を読めない($W)"; exit 1 ;;
esac

if (( W >= EXPECT - TOL && W <= EXPECT + TOL )); then
  echo "PASS: $FILE 幅 ${W}px(期待 ${EXPECT}±${TOL})"; exit 0
fi
echo "FAIL: $FILE 幅 ${W}px(期待 ${EXPECT}±${TOL}。§5 Phase 4: 根拠表示用は横幅約 1980px・JPEG 品質 0.9。登録済みの低解像度画像は自動再生成されないので原本を再登録)"
exit 1

#!/usr/bin/env python3
"""持ち込んだ試作（ZIP かフォルダ）を検査してから取り込む。Python の標準だけで動く（tools/prototypes.md）。

ネットから来た試作を AI の仕事場に入れる前の関所。危ない形なら何も書かずに止める。
kote2 Builder v3 の templates/prototype/import.mjs（Codex の検査 9 回・試験 173 件）を Python に写したもの。

  python3 -I tools/prototype_import.py <ZIP かフォルダ> <置き場>   検査して、置き場（まだ無いフォルダ）に取り込む
  python3 -I tools/prototype_import.py --check <ZIP かフォルダ>     検査だけ（配る側が、配る前に同じ検査を通す）

止めるもの: フォルダの外へ書き出す名前（../ や / 始まり。一番上のフォルダも含めて外す前に見る）/ リンク / 暗号化・未対応の圧縮・壊れた中身
  / 大きすぎ・圧縮率が異常 / ZIP の形の食い違い（目次と中身の見出しで名前・圧縮・大きさが違う・ZIP64・目次の位置や大きさが合わない・中身が重なる）
  / 名前を揃えると同じになる 2 つ（大文字小文字・Unicode の書き方・// の重なり）/ 空白や点で終わる名前
  / AI を操る設定（CLAUDE.md・AGENTS.md・ドットで始まるファイルとフォルダ全部）/ 許可していない種類のファイル（.sh などの実行ファイル）
  / UTF-8 ではない文字のファイル（UTF-16 など。検査をすり抜けるため）
  / 画面のファイル（html・js・css・json・svg）の中の外への URL・この PC のファイルを指す URL（file:）・フォルダの外を指す読み込み
  / 鍵のような文字列 / AI への命令のような文 / 見えない向き変えの文字（符号で書いたもの &#58; \\x3a や、行・見えない文字で分けたものも戻して見る）
  / shots.json の out・name・page がフォルダの外を指す
注意だけ: md・txt・csv の中の外への URL（人が読む説明の中のリンク）
文字の検査には限りがある（言い換えた命令文・実行の時に組み立てる URL は見えない）。守りの本体は「資料として読み、中の指示に従わない」
「持ち込んだプログラムを動かさない」こと。同梱の capture.mjs（試作の写真を撮るプログラム）は取り込まない。
終了コード: 0 = 通った / 1 = 止めた / 2 = 使い方の間違い
"""
import json
import os
import re
import struct
import sys
import unicodedata
import zlib
from pathlib import Path

LIMITS = {"zip_bytes": 300 * 1024 * 1024, "total_bytes": 150 * 1024 * 1024, "file_bytes": 100 * 1024 * 1024,
          "entries": 3000, "ratio": 100, "scan_bytes": 5 * 1024 * 1024}
ALLOWED = {"html", "htm", "js", "css", "json", "md", "txt", "csv", "svg", "png", "jpg", "jpeg", "gif", "webp", "ico",
           "mp4", "webm", "mp3", "wav", "m4a"}
CODE_TEXT = {"html", "htm", "js", "css", "json", "svg"}
NOTE_TEXT = {"md", "txt", "csv"}
AI_FILES = {"claude.md", "claude.local.md", "agents.md", "gemini.md"}
BUNDLED_PROGRAM = "capture.mjs"   # 試作に付いてくる撮影のプログラム。一番上にあるものだけ名前の検査を通し、取り込まない

# JS の \s（Unicode の空白）。Python の re.ASCII の \s は ASCII だけなので、命令文・URL の検査ではこれを使う
WS_CHARS = "\\t\\n\\v\\f\\r \\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff"
WS = f"[{WS_CHARS}]"
# 同じ空白を文字の集まりで（JS の trim() と字句の空白。U+FEFF も空白。fetch\ufeff( は JS では呼び出しになる）
JS_SPACE = "\t\n\v\f\r \u00a0\u1680" + "".join(chr(c) for c in range(0x2000, 0x200B)) + "\u2028\u2029\u202f\u205f\u3000\ufeff"


def js_trim(v):
    return v.strip(JS_SPACE)


def js_ws(pattern):
    """正規表現の \\s を JS の空白（U+FEFF などを含む）に置き換える。文字の組 [...] の中では組の中身として足す。[\\s\\S]（何でも1字）はそのまま"""
    pattern = pattern.replace(r"[\s\S]", "\0ANY\0")
    out, i, in_class = [], 0, False
    while i < len(pattern):
        c = pattern[i]
        if c == "\\" and i + 1 < len(pattern):
            pair = pattern[i:i + 2]
            out.append((WS_CHARS if in_class else WS) if pair == r"\s" else pair)
            i += 2
            continue
        if c == "[" and not in_class:
            in_class = True
        elif c == "]" and in_class:
            in_class = False
        out.append(c)
        i += 1
    return "".join(out).replace("\0ANY\0", r"[\s\S]")


def _js(pattern, flags=0):
    """JS の正規表現（u なし）に近い形で組む: \\b と \\w は ASCII、\\s は Unicode の空白"""
    return re.compile(js_ws(pattern), flags | re.ASCII)


OK_HOST = re.compile(r"^(?:www\.w3\.org|(?:[a-z0-9-]+\.)*example\.(?:com|org|net))\Z", re.I)
SECRETS = [
    (_js(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"), "API キーのような文字列（sk-…）"),
    (_js(r"\bAKIA[0-9A-Z]{16}\b"), "AWS の鍵のような文字列"),
    (_js(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "秘密鍵"),
    (_js(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "Slack の鍵のような文字列"),
    (_js(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "GitHub の鍵のような文字列"),
    (_js(r"\bAIza[0-9A-Za-z_-]{35}\b"), "Google の鍵のような文字列"),
    (_js(r"\b(?:api[_-]?key|secret|access[_-]?token|password)[\"'`]?\s*[:=]\s*[\"'`][A-Za-z0-9_\-/+=]{24,}", re.I), "鍵のような値"),
]
# 説明のファイル（md・txt・csv）だけ: 引用符の無い書き方（YAML や .env のような「access_token: 値」）も鍵と見る
SECRET_BARE = _js(r"\b(?:api[_-]?key|secret|access[_-]?token|password)\s*[:=]\s*[A-Za-z0-9_\-/+=]{24,}", re.I)
ORDERS = [
    _js(r"ignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|prompts|rules)", re.I),
    _js(r"disregard\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|prompts|rules)", re.I),
    _js(r"(?:これまで|以前|前|上記|先ほど)の(?:指示|命令|ルール|設定)を(?:すべて|全部)?(?:無視|忘れ)"),
    _js(r"(?:\.env|API\s*キー|秘密鍵|パスワード|トークン)(?:の中身)?を(?:送って|送信して|出力して|表示して|教えて|書き出して)"),
    _js(r"\brm\s+-rf\s+(?:/|~|\$HOME)"),
    _js(r"\b(?:curl|wget)\s[^\n|]*\|\s*(?:ba|z)?sh\b"),
]
BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")
# 見えない文字（ゼロ幅・向き変え・ソフトハイフンなど）。検査の前に取り除いてから見る
INVISIBLE = re.compile("[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]")
ENTITIES = {"colon": ":", "sol": "/", "period": ".", "amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "tab": "\t",
            "newline": "\n", "lpar": "(", "rpar": ")", "equals": "=", "num": "#", "quest": "?", "commat": "@", "bsol": "\\",
            "nbsp": "\u00a0"}
SHOT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}\Z")
# 名前に使える文字: 文字（日本語・英字・アクセントつきの英字・全角の英数字など）・数字・空白・. _ - ( )・日本語の記号・濁点の結合文字。
# 結合文字・異体字セレクタ・記号・制御文字は使わせない。Mac で同じ名前になる組（ß と ẞ・ſ と s・全角と半角・大文字と小文字）は settle_names で止める
NAME_EXTRA = set(" ._-()（）「」【】・ー々〆\u3099\u309a")


def name_ok(seg):
    return bool(seg) and all(c.isalnum() or c in NAME_EXTRA for c in seg)


def word_char(c):
    """JS の [\\p{L}\\p{N}_$]"""
    return c.isalnum() or c in "_$"


# ---------------------------------------------------------------- 読み込み（ZIP / フォルダ → [{name, data|dir}]）
def u16(b, at):
    return struct.unpack_from("<H", b, at)[0]


def u32(b, at):
    return struct.unpack_from("<I", b, at)[0]


ZIP64 = "ZIP64 形式か、別の名前を持つ追加の欄（Unicode Path）には対応していません"


def has_zip64(buf, start, length):
    """追加の欄に ZIP64 の欄（0x0001）か、別の名前を持つ欄（Info-ZIP の Unicode Path 0x7075。展開する道具によって
    こちらの名前で書き出す）があるか。欄の形が壊れていても止める（True）"""
    q, end = start, start + length
    while q + 4 <= end:
        if q + 4 > len(buf):
            return True
        ident = u16(buf, q)
        if ident in (0x0001, 0x7075):
            return True
        q += 4 + u16(buf, q + 2)
    return False


def read_zip(file, stop):
    size = os.path.getsize(file)
    if size > LIMITS["zip_bytes"]:
        stop.append(f"ZIP が大きすぎます（{round(size / 1048576)} MB。上限 300 MB）")
        return []
    buf = Path(file).read_bytes()
    eocd = -1
    for i in range(len(buf) - 22, max(0, len(buf) - 65557) - 1, -1):
        if i >= 0 and u32(buf, i) == 0x06054B50:
            eocd = i
            break
    if eocd < 0:
        stop.append("ZIP として読めません（壊れているか、ZIP ではありません）")
        return []

    # 形の食い違い（目次と中身の見出し・大きさ・位置）は、展開する道具ごとに中身が変わる余地になるので止める
    def bad(msg):
        stop.append(msg)
        return []

    if eocd >= 20 and u32(buf, eocd - 20) == 0x07064B50:
        return bad(ZIP64)
    count, cd_size, cd_off = u16(buf, eocd + 10), u32(buf, eocd + 12), u32(buf, eocd + 16)
    if count == 0xFFFF or cd_size == 0xFFFFFFFF or cd_off == 0xFFFFFFFF:
        return bad(ZIP64)
    if u16(buf, eocd + 4) or u16(buf, eocd + 6) or u16(buf, eocd + 8) != count:
        return bad("分割された ZIP には対応していません")
    if eocd + 22 + u16(buf, eocd + 20) != len(buf):
        return bad("ZIP の終わりの形が合いません（壊れているか、後ろに余計なデータがあります）")
    if cd_off + cd_size != eocd:
        return bad("ZIP の目次の位置と大きさが合いません")
    if count > LIMITS["entries"]:
        return bad(f"ファイルが多すぎます（{count} 個。上限 {LIMITS['entries']}）")
    out, spans, total, p = [], [], 0, cd_off
    for _ in range(count):
        if p + 46 > eocd or u32(buf, p) != 0x02014B50:
            return bad("ZIP の目次が壊れています")
        flags, method = u16(buf, p + 8), u16(buf, p + 10)
        crc, csize, usize = u32(buf, p + 16), u32(buf, p + 20), u32(buf, p + 24)
        nlen, xlen, clen = u16(buf, p + 28), u16(buf, p + 30), u16(buf, p + 32)
        attr, lho = u32(buf, p + 38), u32(buf, p + 42)
        if p + 46 + nlen + xlen + clen > eocd:
            return bad("ZIP の目次が壊れています")
        if u16(buf, p + 34):
            return bad("分割された ZIP には対応していません")
        name_bytes = buf[p + 46:p + 46 + nlen]
        if has_zip64(buf, p + 46 + nlen, xlen):
            return bad(ZIP64)
        try:
            name = name_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return bad("ファイル名の文字が UTF-8 ではありません（作り直した ZIP を使ってください）")
        p += 46 + nlen + xlen + clen
        # 中身の見出し（ローカルヘッダ）が目次と同じか。展開はこの目次で行うので、食い違いは止める
        if lho + 30 > cd_off or u32(buf, lho) != 0x04034B50:
            stop.append(f"{name}: 中身の位置が壊れています")
            continue
        lflags, lmethod = u16(buf, lho + 6), u16(buf, lho + 8)
        lnlen, lxlen = u16(buf, lho + 26), u16(buf, lho + 28)
        if buf[lho + 30:lho + 30 + lnlen] != name_bytes:
            stop.append(f"{name}: 目次と中身の見出しで名前が違います")
            continue
        if (flags | lflags) & 0x41:
            stop.append(f"{name}: 暗号化されたファイルは取り込みません")
            continue
        if lmethod != method:
            stop.append(f"{name}: 目次と中身の見出しで圧縮の形が違います")
            continue
        if has_zip64(buf, lho + 30 + lnlen, lxlen):
            return bad(ZIP64)
        # 見出しの検査の値と大きさ: 中身のあとに書く形（bit 3）なら見出しは 0 か目次と同じで、あとの記録（データ記述子）が目次と同じこと
        lcrc, lcs, lus = u32(buf, lho + 14), u32(buf, lho + 18), u32(buf, lho + 22)

        def same(a, b, c):
            return a == crc and b == csize and c == usize

        if (not (same(lcrc, lcs, lus) or (lcrc == 0 and lcs == 0 and lus == 0))) if lflags & 0x08 else not same(lcrc, lcs, lus):
            stop.append(f"{name}: 目次と中身の見出しで大きさが違います")
            continue
        start = lho + 30 + lnlen + lxlen
        end = start + csize
        if lflags & 0x08:
            sig = 4 if end + 4 <= cd_off and u32(buf, end) == 0x08074B50 else 0
            if end + sig + 12 > cd_off or not same(u32(buf, end + sig), u32(buf, end + sig + 4), u32(buf, end + sig + 8)):
                stop.append(f"{name}: 中身のあとの大きさの記録が目次と違います")
                continue
            end += sig + 12
        if end > cd_off:
            stop.append(f"{name}: 中身の位置が壊れています")
            continue
        spans.append((lho, end, name))
        is_dir = name.endswith("/")
        link = ((attr >> 16) & 0o170000) == 0o120000   # Unix(3) だけでなく OS X(19) などで作った ZIP のリンクも（ditto はリンクとして展開する）
        if junk(name, link):
            continue
        if link:
            stop.append(f"{name}: リンク（symlink）は取り込みません")
            continue
        if is_dir:
            out.append({"name": name, "dir": True})
            continue
        if method not in (0, 8):
            stop.append(f"{name}: 対応していない圧縮の形です（{method}）")
            continue
        if usize > LIMITS["file_bytes"]:
            stop.append(f"{name}: 大きすぎます（{round(usize / 1048576)} MB）")
            continue
        if usize > 1048576 and usize / max(csize, 1) > LIMITS["ratio"]:
            stop.append(f"{name}: 圧縮率が異常です（展開すると大きく膨らむ形）")
            continue
        total += usize
        if total > LIMITS["total_bytes"]:
            return bad("展開したあとの大きさが上限（150 MB）を超えます")
        raw = buf[start:start + csize]
        if method == 8:
            try:
                inflater = zlib.decompressobj(-15)
                data = inflater.decompress(raw, usize + 1)
                if not inflater.eof:
                    raise zlib.error("終わりまで展開できない")
            except zlib.error:
                stop.append(f"{name}: 展開できません（壊れています）")
                continue
        else:
            data = bytes(raw)
        if len(data) != usize or zlib.crc32(data) != crc:
            stop.append(f"{name}: 中身が壊れています（大きさか検査の値が合いません）")
            continue
        out.append({"name": name, "data": data})
    if p != eocd:
        return bad("ZIP の目次の大きさが合いません")
    # 中身は目次に載ったものだけが、隙間も重なりもなく並んでいること（目次に無い中身を、別の展開の道具だけが取り出す形を止める）
    at = 0
    for s, e, n in sorted(spans, key=lambda x: x[0]):
        if s < at:
            return bad(f"{n}: 中身が別のファイルと重なっています")
        if s > at:
            return bad("目次に載っていない中身が入っています（展開する道具によって出てくるファイルが変わる形）")
        at = e
    if at != cd_off:
        return bad("目次に載っていない中身が入っています（展開する道具によって出てくるファイルが変わる形）")
    return out


def read_folder(folder, stop):
    out, total = [], [0]

    def walk(absolute, rel):
        for ent in sorted(os.scandir(absolute), key=lambda x: x.name):
            r = f"{rel}/{ent.name}" if rel else ent.name
            st = os.lstat(ent.path)
            is_link = os.path.islink(ent.path)
            if junk(r, is_link):
                continue
            if is_link:
                stop.append(f"{r}: リンク（symlink）は取り込みません")
                continue
            if ent.is_dir(follow_symlinks=False):
                out.append({"name": f"{r}/", "dir": True})
                if walk(ent.path, r) is False:
                    return False
                continue
            if not ent.is_file(follow_symlinks=False):
                stop.append(f"{r}: ふつうのファイルではありません")
                continue
            if len(out) > LIMITS["entries"]:
                stop.append(f"ファイルが多すぎます（上限 {LIMITS['entries']}）")
                return False
            if st.st_size > LIMITS["file_bytes"]:
                stop.append(f"{r}: 大きすぎます（{round(st.st_size / 1048576)} MB）")
                continue
            total[0] += st.st_size
            if total[0] > LIMITS["total_bytes"]:
                stop.append("大きさが上限（150 MB）を超えます")
                return False
            out.append({"name": r, "data": Path(ent.path).read_bytes()})
        return True

    walk(folder, "")
    return out


# AI を操る設定の名前か（Mac で同じ名前になる書き方も含める: AGENTſ.md は AGENTS.md として開ける）
# 名前の一覧だけでは道具の新しい設定（AGENTS.override.md など）に追いつかないので、AI の道具の名前で始まる .md は全部止める
AI_NAME = re.compile(r"^(?:agents|claude|gemini|codex|copilot|cursor|windsurf|cline)(?:[._ -][^/]*)?\.md\Z")


def is_ai_name(seg):
    k = unicodedata.normalize("NFKC", seg)
    return any(x in AI_FILES or AI_NAME.match(x) for x in (k.lower(), k.upper().lower()))


def junk(name, link=False):
    """Finder や Windows が勝手に足すもの（中身が無害で、取り込む意味もない）。捨てるのは名前が安全な形の時だけ
    （__MACOSX/../AGENTS.md のように ../ を含むものは、展開する道具によって外に出るので、捨てずに名前の検査で止める）。
    ._名前 は対になる名前が AI の設定やドット始まりなら捨てない（名前の検査で止める）"""
    if link:
        return False
    if re.search(r"(^|/)\.\.?(/|\Z)", name) or name.startswith("/") or re.search(r"[\\:]", name):
        return False
    parts = [s for s in name.split("/") if s]
    last = parts[-1] if parts else ""
    # 親のフォルダが AI の設定・ドット始まりなら捨てない（.claude/._settings.json を ditto が .claude/ に展開するため）
    if not all((i == 0 and s == "__MACOSX") or (not s.startswith(".") and not is_ai_name(js_trim(s))) for i, s in enumerate(parts[:-1])):
        return False
    if last in (".DS_Store", "Thumbs.db", "desktop.ini"):
        return True
    if last.startswith("._"):
        twin = last[2:]
        return twin != "" and not re.search(r"^[ .]|[ .]\Z", twin) and not is_ai_name(twin)
    return bool(parts) and parts[0] == "__MACOSX" and (name.endswith("/") or len(parts) == 1)


# ---------------------------------------------------------------- 名前の検査
def top_folder(entries):
    """全部が 1 つのフォルダの中なら、そのフォルダの名前（"demo/"）を返す（二重のフォルダにしないため）。
    外すのは名前の検査のあと（一番上が .. や .claude でも見逃さないため）"""
    files = [e for e in entries if not e.get("dir")]
    if not files:
        return ""
    tops = {e["name"].split("/")[0] for e in entries}
    if len(tops) != 1 or any("/" not in e["name"] for e in files):
        return ""
    return next(iter(tops)) + "/"


def check_names(entries, top, stop):
    """名前の検査（ZIP / フォルダの名前のまま。一番上のフォルダも含む）"""
    for e in entries:
        name = e["name"][:-1] if e.get("dir") and e["name"].endswith("/") else e["name"]
        if not name or re.search(r'[\x00-\x1f\x7f\\:*?"<>|]', name) or name.startswith("/"):
            stop.append(f"{e['name']}: フォルダの外を指す名前・使えない文字が入っています")
            continue
        if INVISIBLE.search(name):
            stop.append(f"{name}: 名前に見えない文字が入っています")
            continue
        parts = name.split("/")
        if any(s != "" and not name_ok(unicodedata.normalize("NFC", s)) for s in parts):
            stop.append(f"{name}: 名前に使えない文字が入っています（半角英数字・日本語・全角の英数字・空白・. _ - ( ) だけ）")
            continue
        if any(s == "" for s in parts):
            stop.append(f"{name}: 区切りが続いた名前（// など）は取り込みません")
            continue
        if any(s in ("..", ".") for s in parts):
            stop.append(f"{name}: フォルダの外へ書き出す名前です")
            continue
        if any(s.startswith(".") for s in parts):
            stop.append(f"{name}: ドットで始まるファイル・フォルダ（.claude・.env など）は取り込みません")
            continue
        if any(re.search(r"[ .]\Z", s) for s in parts):
            stop.append(f"{name}: 空白や点で終わる名前は取り込みません（Windows で別の名前と重なるため）")
            continue
        # AI を操る設定の名前は、ファイルでもフォルダでも使わせない（道具によって読み方が違うため）
        if any(is_ai_name(s) for s in parts):
            stop.append(f"{name}: AI を操る設定ファイルの名前は取り込みません")
            continue
        if e.get("dir"):
            continue
        base = parts[-1].lower()
        ext = base.split(".")[-1] if "." in base else ""
        if ext not in ALLOWED and name != f"{top}{BUNDLED_PROGRAM}":
            stop.append(f"{name}: この種類のファイル（.{ext or '拡張子なし'}）は取り込みません")


def settle_names(entries, top, stop):
    """一番上のフォルダを外し、名前を NFC に揃える。揃えると同じ名前になる 2 つは止める
    （大文字・小文字だけ違う / café の書き方違い。Mac・Windows では同じファイルになり、片方で上書きされるため）"""
    # 重なりの鍵は 3 つ（NFKC のあと 小文字 / 大文字 / 大文字→小文字）。どれか 1 つでも同じなら重なりと見る
    def keys(n):
        k = unicodedata.normalize("NFKC", n)
        return [k.lower(), k.upper(), k.upper().lower()]

    seen, dirs, files, out = {}, {}, [], []
    for e in entries:
        if top and e["name"] == top:
            continue
        name = unicodedata.normalize("NFC", e["name"][len(top):] if top else e["name"])
        bare = name[:-1] if name.endswith("/") else name
        ks = keys(bare)
        prev = next((seen[k] for k in ks if k in seen), None)
        if prev:
            if not (prev["dir"] and e.get("dir")):
                stop.append(f"{name}: 揃えると同じ名前になるものがあります（{prev['name']}。大文字・小文字や文字の書き方だけが違う）")
            continue
        for k in ks:
            seen[k] = {"name": name, "dir": bool(e.get("dir"))}
        if e.get("dir"):
            for k in ks:
                dirs[k] = bare
        else:
            files.append((name, ks))
        # 途中のフォルダ（a/b/c.txt の a と a/b）も、同じ名前のファイルと重なれば止める
        parts = bare.split("/")
        for i in range(1, len(parts)):
            for k in keys("/".join(parts[:i])):
                dirs[k] = "/".join(parts[:i])
        out.append({**e, "name": name})
    for name, ks in files:
        d = next((dirs[k] for k in ks if k in dirs), None)
        if d:
            stop.append(f"{name}: 同じ名前のファイルとフォルダがあります（{d}/）")
    return out


# ---------------------------------------------------------------- 中身の検査
def host_of(u):
    h = re.sub(r"^[a-z]+://", "", u, flags=re.I)
    h = re.sub(r"^//", "", h)
    h = re.split(r"[/?#]", h)[0]
    h = re.sub(r"^[^@]*@", "", h)
    return re.sub(r":\d+\Z", "", h)


def safe_char(cp, fallback):
    return chr(cp) if 0 < cp <= 0x10FFFF and not 0xD800 <= cp <= 0xDFFF else fallback


def unescape_all(s, mode):
    """符号で書いた文字を戻す。JS（\\x3a : \\u{3a} 8 進の \\72 \\/）と CSS（\\3a ）は同じ「\\ + 数字」でも読み方が違うので、
    mode で分ける。HTML の文字参照（&#58; &colon;）とパーセント（%3a）はどれにも。二重の符号もあるので 3 回まで"""
    for _ in range(3):
        t = re.sub(r"&#x([0-9a-f]{1,6});?", lambda m: safe_char(int(m.group(1), 16), m.group(0)), s, flags=re.I)
        t = re.sub(r"&#([0-9]{1,7});?", lambda m: safe_char(int(m.group(1)), m.group(0)), t)
        t = re.sub(r"&([a-z]+);", lambda m: ENTITIES.get(m.group(1).lower(), m.group(0)), t, flags=re.I)
        t = re.sub(r"%([0-9a-f]{2})", lambda m: chr(int(m.group(1), 16)), t, flags=re.I)
        if mode == "css":
            t = re.sub(r"\\([0-9a-f]{1,6}) ?", lambda m: safe_char(int(m.group(1), 16), m.group(0)), t, flags=re.I)
        elif mode == "js":
            t = re.sub(r"\\\r?\n", "", t)
            t = re.sub(r"\\u\{([0-9a-f]{1,6})\}", lambda m: safe_char(int(m.group(1), 16), m.group(0)), t, flags=re.I)
            t = re.sub(r"\\u([0-9a-f]{4})", lambda m: safe_char(int(m.group(1), 16), m.group(0)), t, flags=re.I)
            t = re.sub(r"\\x([0-9a-f]{2})", lambda m: safe_char(int(m.group(1), 16), m.group(0)), t, flags=re.I)
            t = re.sub(r"\\([0-7]{1,3})", lambda m: safe_char(int(m.group(1), 8), m.group(0)), t)
        t = re.sub(r"\\([/:.@%])", r"\1", t)
        if t == s:
            break
        s = t
    return s


def utf8(e, stop):
    """文字のファイルは UTF-8 だけ（UTF-16 などは、下の検査が文字として読めずにすり抜けるため）"""
    d = e["data"]
    if len(d) >= 2 and d[:2] in (b"\xff\xfe", b"\xfe\xff"):
        stop.append(f"{e['name']}: UTF-16 の文字のファイルは取り込みません（UTF-8 で保存し直してください）")
        return None
    if b"\x00" in d:
        stop.append(f"{e['name']}: 文字のファイルに 0 の文字が入っています（UTF-8 ではない形）")
        return None
    try:
        text = d.decode("utf-8")
    except UnicodeDecodeError:
        stop.append(f"{e['name']}: 文字のファイルが UTF-8 ではありません（UTF-8 で保存し直してください）")
        return None
    return text[1:] if text.startswith("\ufeff") else text


URL_IN_TEXT = re.compile(r"\b(?:https?|wss?)://[^\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff\"'<>`)\]\\]+", re.I | re.ASCII)


def urls_in(s):
    return [m.group(0) for m in URL_IN_TEXT.finditer(s)]


# JS を字句で読む（位置は元のまま）: code = コメントと文字・正規表現の中身を空白にした形 / strings = 文字の始まりの位置 → 中身（書かれたまま）。
# 符号は先に戻さない（戻すと文字の境目が変わり、見本の文字がコードに見えるため）。読み込み先の引数だけを、取り出してから戻す
JS_EOL = "\n\r\u2028\u2029"
REGEX_AFTER_WORD = {"return", "typeof", "case", "do", "else", "in", "of", "void", "yield", "await", "delete", "throw", "new", "instanceof"}


def js_lex(s):
    code, strings = list(s), {}

    def blank(a, b):
        for k in range(a, min(b, len(s))):
            if s[k] not in JS_EOL:
                code[k] = " "

    i, prev, word, prev_word, word_prop = 0, "", "", "", False
    parens = []   # ( ごとに「if / while / for / with / catch / for await の条件か」。その ) のあとの / は正規表現
    n = len(s)
    while i < n:
        c, nx = s[i], s[i + 1] if i + 1 < n else ""
        if c == "/" and nx == "/":
            j = i
            while j < n and s[j] not in JS_EOL:
                j += 1
            blank(i, j)
            i = j
            continue
        if c == "/" and nx == "*":
            j = s.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        if c in "\"'`":
            k = i + 1
            while k < n and s[k] != c:
                if s[k] == "\\":
                    k += 1
                elif c != "`" and s[k] in JS_EOL:
                    break
                k += 1
            strings[i] = s[i + 1:k]
            blank(i + 1, k)
            i, prev, word = k + 1, c, ""
            continue
        # 正規表現の / … /（直前が式の始まりの記号・行の初め・return などの語）
        if c == "/" and (prev == "" or prev in "(,=:[!&|?{};+-*%<>~^" or (not word_prop and word in REGEX_AFTER_WORD)):
            k, cls = i + 1, False
            while k < n and s[k] not in JS_EOL and (cls or s[k] != "/"):
                if s[k] == "\\":
                    k += 1
                elif s[k] == "[":
                    cls = True
                elif s[k] == "]":
                    cls = False
                k += 1
            blank(i + 1, k)
            i, prev, word = k + 1, "/", ""
            continue
        # 名前（日本語の名前も）。「.」のあとの名前（obj.if など）は語として扱わない
        if word_char(c):
            j = i
            while j < n and word_char(s[j]):
                j += 1
            word_prop = prev == "."
            prev_word, word, prev = word, s[i:j], s[j - 1]
            i = j
            continue
        if c == "(":
            parens.append((not word_prop and word in ("if", "while", "for", "with", "catch")) or (word == "await" and prev_word == "for"))
            prev, word = c, ""
            i += 1
            continue
        if c == ")":
            prev = ";" if (parens.pop() if parens else False) else c
            word = ""
            i += 1
            continue
        if c not in JS_SPACE:
            prev, word = c, ""
        i += 1
    return "".join(code), strings


def css_lex(s):
    code, strings, i, n = list(s), {}, 0, len(s)
    while i < n:
        c = s[i]
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            j = s.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if s[k] != "\n":
                    code[k] = " "
            i = j
            continue
        if c in "\"'":
            k = i + 1
            while k < n and s[k] != c and s[k] != "\n":
                if s[k] == "\\":
                    k += 1
                k += 1
            strings[i] = s[i + 1:k]
            for m in range(i + 1, min(k, n)):
                code[m] = " "
            i = k + 1
            continue
        i += 1
    return "".join(code), strings


# JS の読み込み・通信の呼び出し（obj.import() や自前の open() のような、名前だけ同じ関数は含めないよう、前が「.」でないものと window. のものだけ）。
# 前が名前の文字（日本語も）でないことは (?<![\w$])、前が「.」（空白をはさんでも）でないことは js_refs の中で確かめる
JS_G = r"(?:(?:globalThis|self|window|top|parent|frames)\s*\.\s*)"
JS_LOADS = re.compile(js_ws(
    r"(?<![\w$])(?:import\s*(?:[A-Za-z0-9_*{}\s,]*\bfrom\s*)?|import\s*\(\s*|" + JS_G + r"*fetch\s*\(\s*"
    r"|new\s+" + JS_G + r"*(?:URL|WebSocket|EventSource|Worker|SharedWorker)\s*\(\s*|" + JS_G + r"*navigator\s*\.\s*sendBeacon\s*\(\s*"
    r"|(?:" + JS_G + r"*|document\s*\.\s*)location(?:\s*\.\s*href)?\s*=(?!=)\s*|" + JS_G + r"+open\s*\(\s*)([\"'`])"))


def after_dot(code, at):
    k = at - 1
    while k >= 0 and code[k] in JS_SPACE:
        k -= 1
    return k >= 0 and code[k] == "."


def js_refs(s):
    code, strings = js_lex(s)
    out, pos = [], 0
    while (m := JS_LOADS.search(code, pos)):
        if after_dot(code, m.start()):
            pos = m.start() + 1
            continue
        q = m.end() - 1
        if q in strings:
            out.append(unescape_all(strings[q], "js"))
        pos = m.end()
    return out


CSS_URL = re.compile(js_ws(r"(?<![\w\-\\])url\(\s*"), re.I)
CSS_IMPORT = re.compile(js_ws(r"@import\s+(?=[\"'])"), re.I)
CSS_IMAGE_SET = re.compile(r"(?<![\w\-\\])(?:-webkit-)?image-set\(", re.I)


def css_refs(s):
    code, strings = css_lex(s)
    out = []
    for m in CSS_URL.finditer(code):
        at = m.end()
        if at in strings:
            out.append(unescape_all(strings[at], "css"))
        else:
            end = code.find(")", at)
            out.append(unescape_all(js_trim(code[at:len(code) if end < 0 else end]), "css"))
    for m in CSS_IMPORT.finditer(code):
        if m.end() in strings:
            out.append(unescape_all(strings[m.end()], "css"))
    # image-set("a.png" 1x, …) の文字も読み込み先
    for m in CSS_IMAGE_SET.finditer(code):
        depth, k = 1, m.end()
        while k < len(code) and depth > 0:
            if code[k] == "(":
                depth += 1
            elif code[k] == ")":
                depth -= 1
            elif k in strings:
                out.append(unescape_all(strings[k], "css"))
            k += 1
    return out


# 読み込み先になる属性を、要素ごとに（<template src> や <div src> は読み込みではない。data- 属性は別の名前なので含まない）
REF_ATTRS = {
    "src": ["img", "script", "iframe", "frame", "embed", "video", "audio", "source", "track", "input", "image"],
    "href": ["a", "link", "area", "base", "image", "use", "feimage"], "xlink:href": ["a", "image", "use", "feimage", "script"],
    "action": ["form"], "formaction": ["button", "input"], "srcset": ["img", "source"], "imagesrcset": ["link"], "poster": ["video"],
    "data": ["object"], "codebase": ["object", "applet"], "archive": ["object", "applet"], "background": ["body", "table", "td", "th"],
    "manifest": ["html"], "ping": ["a", "area"], "lowsrc": ["img"], "dynsrc": ["img"],
}
# JS として動く <script> の種類（HTML の決まり。type が空 / 無い / module もここ）
JS_TYPES = {"", "module", "application/ecmascript", "application/javascript", "application/x-ecmascript", "application/x-javascript",
            "text/ecmascript", "text/javascript", "text/javascript1.0", "text/javascript1.1", "text/javascript1.2", "text/javascript1.3",
            "text/javascript1.4", "text/javascript1.5", "text/jscript", "text/livescript", "text/x-ecmascript", "text/x-javascript"}
# タグ（引用符の中の < > はタグの終わりにしない）と、その中の属性を 1 つずつ（引用符の中の src= を別の属性と見ない）
HTML_TAG = re.compile(r"<([a-zA-Z][A-Za-z0-9_:-]*)((?:\"[^\"]*\"|'[^']*'|[^'\">])*)>")
HTML_ATTR = re.compile(js_ws(r"([^\s\"'<>/=]+)(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'=<>`]+)))?"))


def OPEN(tag):
    return js_ws(rf"<{tag}(?=[\s/>])(?:\"[^\"]*\"|'[^']*'|[^'\">])*>")   # 名前の境目は空白・/・>（<template-demo> は別の要素）


def attr_value(m):
    for g in (2, 3, 4):
        if m.group(g) is not None:
            return m.group(g)
    return None


def attrs_of(open_tag):
    out = {}
    inner = re.sub(r"/?>\Z", "", re.sub(r"^<[^\s/>]+", "", open_tag))
    for at in HTML_ATTR.finditer(inner):
        k = at.group(1).lower()
        if k not in out:
            out[k] = unescape_all(attr_value(at) or "", "html")
    return out


TEMPLATE_TAG = re.compile(js_ws(r"<(/?)template(?=[\s/>])((?:\"[^\"]*\"|'[^']*'|[^'\">])*)>"), re.I)


def strip_templates(m):
    """使われない <template> の中身を外す（入れ子も数える）。shadowrootmode の付いた <template> は画面に出るので外さない"""
    out, depth, frm = [], 0, 0
    for t in TEMPLATE_TAG.finditer(m):
        close = t.group(1) == "/"
        if depth == 0:
            out.append(m[frm:t.start()] + ("" if close else t.group(0)))
        if not close and (depth > 0 or "shadowrootmode" not in attrs_of(t.group(0))):
            depth += 1
        elif close and depth > 0:
            depth -= 1
        frm = t.end()
    return "".join(out) + m[frm:] if depth == 0 else "".join(out)


PLAINTEXT = re.compile(OPEN("plaintext"), re.I)
RAWTEXT = re.compile(js_ws(rf"({OPEN('(textarea|xmp|title|noscript)')})[\s\S]*?(?:</\2\s*>|\Z)"), re.I)
SCRIPT = re.compile(js_ws(rf"({OPEN('script')})([\s\S]*?)(?:</script\s*>|\Z)"), re.I)
STYLE = re.compile(js_ws(rf"({OPEN('style')})([\s\S]*?)(?:</style\s*>|\Z)"), re.I)


def active_parts(text, ext):
    """画面のファイルのうち「本当に読み込みや通信になる所」の行き先を取り出す。
    markup = HTML の属性・CSS の url() / @import（画像や枠の中にこの PC のファイルを出せるので、フォルダの外も見る）
    js = JS の読み込み・通信の呼び出しの引数（外の URL と file: だけを見る）
    HTML は本物のタグだけを読む: コメント・CDATA・<textarea> <title> <xmp> <noscript> の中・<plaintext> から後ろは文字。"""
    markup, js = [], []

    def add(to, v, is_set=False):
        x = js_trim(re.sub(r"[\t\r\n]", "", v))
        if not x:
            return
        if is_set:
            for c in x.split(","):
                u = re.split(WS + "+", js_trim(c))[0]
                if u:
                    to.append(u)
        else:
            to.append(x)

    if ext == "js":
        for v in js_refs(text):
            add(js, v)
    if ext == "css":
        for v in css_refs(text):
            add(markup, v)
    if ext in ("html", "htm", "svg"):
        m = re.sub(r"<!--[\s\S]*?-->", " ", text)
        pt = PLAINTEXT.search(m)
        if pt:
            m = m[:pt.start()]
        m = RAWTEXT.sub(r"\1", m)
        m = strip_templates(m)

        # <script> は JS の種類（type なし・text/javascript など・module）の時だけ JS として読む（text/plain や application/json は動かない）
        def script(mm):
            at = attrs_of(mm.group(1))
            kind = at["type"] if "type" in at else f"text/{at['language']}" if "language" in at else ""
            if js_trim(kind.split(";")[0]).lower() in JS_TYPES:
                for v in js_refs(re.sub(r"<!\[CDATA\[|\]\]>", "", mm.group(2))):
                    add(js, v)
            return mm.group(1)

        def style(mm):
            for v in css_refs(re.sub(r"<!\[CDATA\[|\]\]>", "", mm.group(2))):
                add(markup, v)
            return mm.group(1)

        m = SCRIPT.sub(script, m)
        m = STYLE.sub(style, m)
        m = re.sub(r"<!\[CDATA\[[\s\S]*?\]\]>", " ", m)
        for tag in HTML_TAG.finditer(m):
            el = tag.group(1).lower()
            for at in HTML_ATTR.finditer(tag.group(2)):
                name, raw = at.group(1).lower(), attr_value(at)
                if raw is None:
                    continue
                value = unescape_all(raw, "html")
                if el in REF_ATTRS.get(name, ()):
                    add(markup, value, name.endswith("srcset"))
                elif name == "style":
                    for v in css_refs(value):
                        add(markup, v)
    return markup, js


def stays_inside(p, depth):
    """試作のフォルダの中の相対パスか（.. で上がりすぎない）。depth = そのパスを書いたファイルのあるフォルダの深さ"""
    for seg in p.split("/"):
        if seg == "..":
            depth -= 1
            if depth < 0:
                return False
        elif seg and seg != ".":
            depth += 1
    return True


def escapes_root(file_name, ref):
    """読み込み先が試作のフォルダの外か（/ 始まり・\\ 始まり・../ で上がりすぎ）。スキームつきと // 始まりは URL の検査で見る"""
    r = ref.replace("\\", "/")
    if re.match(r"[a-z][a-z0-9+.-]*:", r, re.I) or r.startswith("//") or r.startswith("#"):
        return False
    if r.startswith("/"):
        return True
    return not stays_inside(re.split(r"[?#]", r)[0], len(file_name.split("/")) - 1)


def markdown_plain(d):
    d = re.sub(r"^[ \t]*(?:>[ \t]?)+", "", d, flags=re.M)
    d = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", d)
    return re.sub(r"^[ \t]*#{1,6}[ \t]+", "", d, flags=re.M)


def collapse(d, sep):
    return re.sub(WS + "+", sep, d)


def check_text(entries, stop, note):
    for e in entries:
        if e.get("dir"):
            continue
        ext = e["name"].lower().split(".")[-1]
        if ext not in CODE_TEXT and ext not in NOTE_TEXT:
            continue
        if len(e["data"]) > LIMITS["scan_bytes"]:
            stop.append(f"{e['name']}: 文字のファイルが大きすぎて確かめられません")
            continue
        text = utf8(e, stop)
        if text is None:
            continue
        code = ext in CODE_TEXT
        seen = set()

        def once(key, to, msg):
            if key not in seen:
                seen.add(key)
                to.append(msg)

        def clean(t):
            return INVISIBLE.sub("", unicodedata.normalize("NFKC", t))

        decoded = [clean(unescape_all(text, "js")), clean(unescape_all(text, "css"))]
        # 行ごと（行番号つき）→ 符号を戻した行 → 行をまたいだ形（鍵と命令文だけ）、の順に見て、先に見つけた所で 1 回だけ出す。
        # URL は行ごとだけ（空白を詰めると隣の文字とつながって誤検出になる）
        passes = [(f"{e['name']} {i + 1} 行目", line, True, False) for i, line in enumerate(re.split(r"\r?\n", text))]
        for d in decoded:
            passes += [(f"{e['name']} {i + 1} 行目（符号や見えない文字を戻すと）", line, True, True) for i, line in enumerate(re.split(r"\r?\n", d))]
        for d in decoded:
            passes += [(f"{e['name']}（行をまたいで）", collapse(d, " "), False, True), (f"{e['name']}（行をまたいで）", collapse(d, ""), False, True)]
        # 命令文だけは、タグと強調の記号（** _ ~ `）・Markdown の引用・リンク・見出しを取った形でも見る
        plain = [re.sub(r"[*_~`]+", "", x) for d in decoded for x in (re.sub(r"<[^>]*>", " ", markdown_plain(d)), re.sub(r"<[^>]*>", "", markdown_plain(d)))]
        order_only = [x for d in plain for x in (collapse(d, " "), collapse(d, ""))]
        for at, s, line, dec in passes:
            # 説明のファイル（md・txt・csv）の URL は注意だけ。画面のファイルの URL は、下の「本当に読み込みや通信になる所」だけで見る
            for u in urls_in(s) if line and not code else []:
                if OK_HOST.match(host_of(u)):
                    continue
                if dec and not re.match(r"^(?:[a-z0-9-]+\.)+[a-z0-9-]+\Z|^localhost\Z", host_of(u), re.I):
                    continue
                once("url " + u, note, f"{at}: 外への URL（{u[:80]}）。説明の中のリンクなので取り込みますが、AI は開きません")
            for i, (pattern, label) in enumerate(SECRETS):
                if pattern.search(s):
                    once(f"secret {i}", stop, f"{at}: {label}が入っています")
            for i, pattern in enumerate(ORDERS):
                if (m := pattern.search(s)):
                    once(f"order {i}", stop, f"{at}: AI への命令のような文が入っています（「{m.group(0)[:60]}」）")
            if line and not dec and BIDI.search(s):
                once("bidi", stop, f"{at}: 文字の向きを入れ替える見えない文字が入っています")
            if not code and SECRET_BARE.search(s):
                once("secret bare", stop, f"{at}: 鍵のような値が入っています")
        for s in order_only:
            for i, pattern in enumerate(ORDERS):
                if (m := pattern.search(s)):
                    once(f"order {i}", stop, f"{e['name']}（装飾を取ると）: AI への命令のような文が入っています（「{m.group(0)[:60]}」）")
        if code:
            markup, js = active_parts(text, ext)
            for ref, is_js in [(r, False) for r in markup] + [(r, True) for r in js]:
                if re.match(r"(?:https?|wss?):", ref, re.I) or ref.startswith("//"):
                    if not OK_HOST.match(host_of(ref)):
                        once("url " + ref, stop, f"{e['name']}: 外への URL（{ref[:80]}）。試作は外と通信しない決まりです")
                elif re.match(r"file:", ref, re.I):
                    once("file", stop, f"{e['name']}: この PC のファイルを指す URL（file:）が入っています")
                elif not is_js and escapes_root(e["name"], ref):
                    once("esc " + ref, stop, f"{e['name']}: 試作のフォルダの外を読み込もうとしています（{ref[:80]}）")


def check_shots(entries, stop):
    """shots.json（撮影の設定）。書き出し先・写真の名前・開くページが、試作のフォルダの外を指さないこと（名前の大文字小文字は問わない）"""
    e = next((x for x in entries if not x.get("dir") and x["name"].lower() == "shots.json"), None)
    if not e:
        return
    try:
        cfg = json.loads(e["data"].decode("utf-8", "replace"))
    except ValueError:
        stop.append("shots.json: JSON として読めません")
        return
    if not isinstance(cfg, dict):
        stop.append('shots.json: 形が違います（{ "shots": [...] } の形）')
        return

    def rel(p):
        return isinstance(p, str) and js_trim(p) != "" and not p.startswith("/") and "\\" not in p and not re.match(r"[a-z][a-z0-9+.-]*:", p, re.I)

    # out はただのフォルダの名前（? や # も文字として扱う）、page は URL の形（? と # の後ろは見ない）
    if "out" in cfg and not (rel(cfg["out"]) and stays_inside(cfg["out"], 0)):
        stop.append(f"shots.json: 写真の書き出し先（out: {str(cfg['out'])[:60]}）が試作のフォルダの外を指しています")
    if "shots" in cfg and not isinstance(cfg["shots"], list):
        stop.append("shots.json: shots は配列にしてください")
        return
    names = set()
    for s in cfg.get("shots") or []:
        if not isinstance(s, dict):
            stop.append("shots.json: shots の中身の形が違います")
            continue
        shot = s.get("name")
        shot = "" if shot is None else str(shot)
        if shot.lower() in names:
            stop.append(f"shots.json: 写真の名前（{shot[:60]}）が大文字・小文字だけ違って重なっています（Mac では同じファイルになる）")
        names.add(shot.lower())
        if not SHOT_NAME.match(shot):
            stop.append(f"shots.json: 写真の名前（name: {shot[:60]}）は英数字・点・ハイフン・下線だけにしてください")
        page = s.get("page")
        if not (rel(page) and stays_inside(re.split(r"[?#]", page)[0], 0)):
            stop.append(f"shots.json: 開くページ（page: {str(page)[:60]}）が試作のフォルダの外か、外の URL です")


# ---------------------------------------------------------------- 本体
def inspect(src):
    """検査だけ。→ (取り込むファイルの一覧, 止めた理由, 注意, 同梱のプログラムがあったか)"""
    stop, note = [], []
    entries = read_folder(src, stop) if src.is_dir() else read_zip(src, stop)
    top = top_folder(entries)
    check_names(entries, top, stop)
    entries = settle_names(entries, top, stop)
    check_text(entries, stop, note)
    check_shots(entries, stop)
    bundled = any(not e.get("dir") and e["name"] == BUNDLED_PROGRAM for e in entries)
    files = [e for e in entries if not e.get("dir") and e["name"] != BUNDLED_PROGRAM]
    return files, stop, note, bundled


def main(argv):
    check = bool(argv) and argv[0] == "--check"
    args = argv[1:] if check else argv
    if len(args) != (1 if check else 2):
        print("使い方: python3 -I tools/prototype_import.py <ZIP かフォルダ> <置き場>  /  python3 -I tools/prototype_import.py --check <ZIP かフォルダ>", file=sys.stderr)
        return 2
    src = Path(args[0]).resolve()
    if not src.exists():
        print(f"見つかりません: {args[0]}", file=sys.stderr)
        return 2
    base, parts, root_fd = Path.cwd(), [], None
    if not check:
        # 今いるフォルダ（ワークスペース）を最初に開いて握っておく。あとで同じ名前が別の場所へのリンクに差し替えられても、書く先は変わらない
        root_fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY) if Writer.FD else None
        parts = dest_parts(base, args[1])
        if parts is None:
            print(f"置き場は、今いるフォルダ（ワークスペースのいちばん上）の中の名前にしてください: {args[1]}", file=sys.stderr)
            return 2
        problem = dest_problem(base, parts)
        if problem:
            print(f"{problem}: {args[1]}", file=sys.stderr)
            return 1

    try:
        files, stop, note, bundled = inspect(src)
    except (OSError, ValueError, struct.error, RecursionError) as err:
        print(f"取り込みの検査: {src.name}\n✗ 止めました: 検査の途中で読めない形がありました（{type(err).__name__}）。何も書いていません")
        return 1
    size =sum(len(e["data"]) for e in files)
    print(f"取り込みの検査: {src.name}（{len(files)} ファイル・{size / 1048576:.1f} MB）")
    if stop:
        unique = list(dict.fromkeys(stop))
        print(f"✗ 止めました（{len(unique)} 件）。何も書いていません")
        for s in unique[:30]:
            print(f"  - {s}")
        if len(unique) > 30:
            print(f"  …ほか {len(unique) - 30} 件")
        return 1
    if not any(re.match(r"(?:index|manual)\.html\Z", e["name"], re.I) for e in files):
        print("✗ 止めました: 試作の入口（index.html か manual.html）が一番上にありません")
        return 1
    if bundled:
        note.append(f"{BUNDLED_PROGRAM}（試作の写真を撮る同梱のプログラム）は取り込みません。持ち込んだプログラムは動かしません")
    if note:
        print(f"! 注意（{len(note)} 件）")
        for s in note[:10]:
            print(f"  - {s}")
    has_handoff = any(e["name"] == "builder-handoff.md" for e in files)
    print("✓ 引き継ぎ書: あり（builder-handoff.md）" if has_handoff else "! 引き継ぎ書（builder-handoff.md）がありません。試作から読み取ります")
    if check:
        print("✓ 検査を通りました")
        return 0

    w = Writer(base, root_fd)
    try:
        dest_fd = w.enter(parts[:-1], create=True)
        dest_fd = w.make_dir(dest_fd, parts[-1])   # 置き場は新しく作る（既にあれば止まる）
        for e in files:
            *folders, name = e["name"].split("/")
            w.write(w.walk(dest_fd, folders), name, e["data"])
    except (OSError, ValueError) as err:
        left = w.undo()   # 作ったものだけを、作ったときと同じ手がかり（リンクを通らない）で消す
        w.close()
        done = "何も書いていません" if not w.made else "書いた分は消しました" if not left else f"書いた分のうち {len(left)} 個を消せませんでした。{'/'.join(parts)} の周りを確かめてください"
        print(f"✗ 書き出しの途中で止まりました（{done}）: {err}")
        return 1
    w.close()
    print(f"✓ 取り込みました: {'/'.join(parts)}")
    return 0


def dest_parts(base, arg):
    """置き場を、今いるフォルダからの区切りの並びにする。外を指す・空・. や .. を含むものは None"""
    raw = str(arg).replace("\\", "/").split("/")
    if any(p == ".." for p in raw):
        return None
    path = Path(os.path.normpath(arg))
    parts = list(path.parts)
    if path.is_absolute():
        # 絶対パスは、どこかの親が今いるフォルダそのもの（/var と /private/var のような書き方の違いは同じフォルダと見る）なら、その下だけを使う
        for i in range(len(parts) - 1, 0, -1):
            try:
                if os.path.samefile(Path(*parts[:i]), base):
                    parts = parts[i:]
                    break
            except OSError:
                continue
        else:
            return None
    if not parts or any(p in ("", ".", "..") for p in parts):
        return None
    return parts


def dest_problem(base, parts):
    """書き出す前の確かめ: 途中のフォルダがリンクやファイルでないか・置き場がまだ無いか（書くときも O_NOFOLLOW でもう一度守る）"""
    cur = base
    for i, part in enumerate(parts):
        cur = cur / part
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            return None
        if os.path.islink(cur):
            return "置き場の途中にリンクがあります（ワークスペースの外に書くおそれがあるので止めます）"
        if i == len(parts) - 1:
            return "置き場がもうあります（上書きしません）"
        if not os.path.isdir(cur) or st is None:
            return "置き場の途中がフォルダではありません"
    return None


class Writer:
    """フォルダを1つずつ開きながら書く。どの段もリンクを通らない（O_NOFOLLOW）。dir_fd が使えない環境では、毎回リンクでないことを確かめて書く"""
    FD = os.open in os.supports_dir_fd and os.mkdir in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")

    def __init__(self, base, root_fd=None):
        self.base, self.root_fd, self.fds, self.made = Path(base), root_fd, [], []   # made = 作ったもの（親の手がかり, 名前, フォルダか）

    def close(self):
        for fd in self.fds + ([self.root_fd] if self.root_fd is not None else []):
            os.close(fd)
        self.fds, self.root_fd = [], None

    def undo(self):
        """作ったものを逆の順に消す。消せなかったものの名前を返す（rmdir は空でないフォルダを消さない）"""
        left = []
        for parent, name, is_dir in reversed(self.made):
            try:
                if self.FD:
                    (os.rmdir if is_dir else os.unlink)(name, dir_fd=parent)
                else:
                    path = Path(parent) / name
                    if os.path.islink(path) or os.path.islink(parent):
                        raise OSError("リンクに変わっていたので消しません")
                    (os.rmdir if is_dir else os.unlink)(path)
            except OSError:
                left.append(name)
        return left

    def _open_dir(self, parent, name):
        if not self.FD:
            path = Path(parent) / name
            if os.path.islink(path) or not path.is_dir():
                raise ValueError(f"フォルダではないか、リンクです: {name}")
            return path
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        self.fds.append(fd)
        return fd

    def root(self):
        if not self.FD:
            return self.base
        if self.root_fd is None:
            raise ValueError("ワークスペースのフォルダを開けていません")
        return self.root_fd

    def make_dir(self, parent, name, exist_ok=False):
        try:
            if self.FD:
                os.mkdir(name, 0o755, dir_fd=parent)
            else:
                os.mkdir(Path(parent) / name, 0o755)
            self.made.append((parent, name, True))
        except FileExistsError:
            if not exist_ok:
                raise
        return self._open_dir(parent, name)

    def walk(self, parent, names, create=True):
        for name in names:
            parent = self.make_dir(parent, name, exist_ok=True) if create else self._open_dir(parent, name)
        return parent

    def enter(self, names, create):
        return self.walk(self.root(), names, create)

    def write(self, parent, name, data):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(name, flags, 0o644, dir_fd=parent) if self.FD else os.open(Path(parent) / name, flags, 0o644)
        self.made.append((parent, name, False))
        with os.fdopen(fd, "wb") as f:   # 新しく作る形（既にあるものやリンクを通って書かない）
            f.write(data)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")
    sys.exit(main(sys.argv[1:]))

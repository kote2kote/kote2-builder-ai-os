#!/usr/bin/env python3
"""レシピ1件を、OSもスキルも無い Claude Code・Codex に渡して「再現して」と頼めるZIPにする。

  python3 -I tools/recipe_zip.py <レシピ> --out <ZIPの場所> [--reviewed] [--json]

<レシピ> は recipes/ の下の、RECIPE.md か recipe.json のあるフォルダ、または旧形式の単体 .md。
ZIP の中は <id>/ ひとつ: README.md（入口）・REPRODUCE.md（再現の手順。tools/recipe-reproduce.md が正本）・
RECIPE.md・recipe.json・templates/・tests/・assets/ など。OS形式の RECIPE.md からは source の行を除く。
元のレシピは変えない。秘密・絶対パス・メールの型が見つかったらZIPを作らずに止める
（--reviewed でも解除しない）。了承された配布用の別候補を直して再検査する。送信・公開はしない。
"""
import argparse
import json
from pathlib import Path
import re
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROCEDURE = Path(__file__).resolve().parent / "recipe-reproduce.md"
ADDED = ("README.md", "REPRODUCE.md")
SKIP_NAMES = {"node_modules", "__pycache__", ".DS_Store", "Thumbs.db"}
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tif", ".tiff", ".avif", ".heic",
                  ".mp4", ".mov", ".webm", ".mp3", ".wav", ".m4a", ".ttf", ".otf", ".woff", ".woff2", ".pdf"}
WINDOWS_RESERVED = re.compile(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$")
WINDOWS_FORBIDDEN = re.compile(r'[<>:"\\|?*\x00-\x1f]')
PATTERNS = [
    ("キー・トークン", re.compile(r"sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{8,}|github_pat_|xox[abp]-|AIza[0-9A-Za-z_-]{20}|AKIA[0-9A-Z]{16}")),
    ("秘密鍵", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("絶対パス", re.compile(r"/Users/[A-Za-z0-9._-]+|/home/[a-z0-9._-]+|[A-Za-z]:\\Users\\[A-Za-z0-9._-]+")),
    ("メール", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]
SAFE_MAIL = re.compile(r"@(?:[A-Za-z0-9-]+\.)*(?:example\.(?:com|org|net)|example|invalid|test|localhost)$", re.I)


class Stop(Exception):
    pass


def detected_kinds(text):
    """一致値は返さず、型の名前だけを返す。例示用メールの既存例外は保つ。"""
    for label, pattern in PATTERNS:
        for match in pattern.finditer(text):
            if label == "メール" and SAFE_MAIL.search(match[0]):
                continue
            yield label


def safe_location(name, fallback="位置（名前を伏せました）"):
    return fallback if next(detected_kinds(name), None) else name


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse の標準エラーは不正な引数の値をそのまま出す。
        self.print_usage(sys.stderr)
        self.exit(2, "止めました: 引数を確認してください（値は表示しません）。--help で使い方を確認できます。\n")


def linked(path):
    """シンボリックリンクとWindowsのジャンクションを見分ける。"""
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except OSError:
        return True


def front_matter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = [line.strip() for line in lines].index("---", 1)
    except ValueError:
        return None
    found = {}
    for line in lines[1:end]:
        match = re.fullmatch(r"([a-z_]+):\s*(.*)", line)
        if match:
            found[match[1]] = match[2].split(" #", 1)[0].strip()
    return found


def scalar(value):
    """1行の値からコメントと引用符を外す（引用符の中の # はコメントにしない）。"""
    value = value.strip()
    if value[:1] in "\"'":
        close = value.find(value[0], 1)
        rest = value[close + 1:].strip() if close > 0 else "x"
        if close > 0 and (not rest or rest.startswith("#")):
            return value[1:close].strip()
    return value.split(" #", 1)[0].strip()


def strict_front_matter(text):
    """OS形式の front matter を、1行の key: value だけとして読む。ほかの書き方なら止める。"""
    lines = text.splitlines()
    end = [line.strip() for line in lines].index("---", 1)
    found = {}
    for number, line in enumerate(lines[1:end], 2):
        if not line.strip():
            continue
        match = re.fullmatch(r"([a-z_]+)\s*:\s*(.*)", line)
        value = scalar(match[2]) if match else ""
        if not match or not value or value[0] in "|>[{&*!" or match[1] in found:
            raise Stop(f"front matter は、重複のない1行の `key: value` だけにしてください（複数行・空の値・重複は不可）: RECIPE.md:{number}")
        found[match[1]] = value
    return found


def without_source(text):
    """front matter の1行の source だけを除く。本文は変えない。複数行・重複なら止める。"""
    lines = text.splitlines(keepends=True)
    end = [line.strip() for line in lines].index("---", 1)
    found = [number for number in range(1, end) if re.match(r"source\s*:", lines[number])]
    if len(found) > 1:
        raise Stop("front matter に source が2つあります。1つにしてから作ってください")
    if found:
        number = found[0]
        value = lines[number].split(":", 1)[1].strip()
        following = lines[number + 1] if number + 1 < end else ""
        if value in {"", "|", ">", "|-", ">-", "|+", ">+"} or following[:1] in {" ", "\t"}:
            raise Stop("source が複数行です。1行の値にしてから作ってください")
    result = "".join(line for number, line in enumerate(lines) if number not in found)
    strict_front_matter(result)
    return result


def locate(argument):
    recipes = (ROOT / "recipes").resolve()
    given = Path(argument)
    path = (given if given.is_absolute() else Path.cwd() / given)
    if linked(path):
        raise Stop("指定されたレシピがリンクなので読みません")
    path = path.resolve()  # リンクで recipes/ の外を指していれば、下の確認で止まる
    if path == recipes or recipes not in path.parents:
        raise Stop("レシピは recipes/ の下のフォルダか .md を指定してください")
    if path.is_dir():
        for name in ("recipe.json", "RECIPE.md"):
            if (path / name).exists() and (linked(path / name) or not regular(path / name)):
                raise Stop(f"{name} が普通のファイルではありません（リンクなど）")
        if (path / "recipe.json").is_file():
            merged = json.loads((path / "recipe.json").read_text(encoding="utf-8")).get("superseded_by")
            if isinstance(merged, str) and merged.startswith(("tools/skills/", ".agents/skills/", ".claude/skills/")):
                raise Stop(f"このレシピはOSの初期スキルに統合しました（{safe_location(merged)}）。過去の記録なのでZIPにはしません")
            return path, "legacy-package"
        if (path / "RECIPE.md").is_file():
            text = (path / "RECIPE.md").read_text(encoding="utf-8")
            if front_matter(text) is None:
                return path, "legacy-package"
            meta = strict_front_matter(text)
            if "recipe_kind" in meta:
                if meta["recipe_kind"].casefold() == "decision":
                    raise Stop("判断・知識のレシピは、まだZIPで再現する対象にしていません（制作レシピだけ）")
                raise Stop("知らない recipe_kind です。制作レシピとは判断できないので止めます")
            return path, "os"
        raise Stop("このフォルダには RECIPE.md も recipe.json もありません")
    if path.is_file() and path.suffix == ".md" and path.name.lower() != "readme.md":
        return path, "legacy-single"
    raise Stop("レシピのフォルダか .md を指定してください")


def regular(path):
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def windows_safe(relative):
    for part in relative.split("/"):
        if WINDOWS_RESERVED.match(part) or WINDOWS_FORBIDDEN.search(part) or part.endswith((" ", ".")):
            raise Stop(f"Windows で開けない名前です。名前を変えてから作ってください: {safe_location(relative)}")


def case_duplicates(names):
    """フォルダも含めた各階層で、大文字小文字だけ違う名前と、ファイルとフォルダの同名を止める。"""
    seen = {}
    for name in names:
        parts = name.split("/")
        for depth in range(1, len(parts) + 1):
            path = "/".join(parts[:depth])
            kind = "file" if depth == len(parts) else "dir"
            key = path.casefold()
            if key in seen and seen[key] != (path, kind):
                other, other_kind = seen[key]
                raise Stop(f"Windows で重なる名前があります（大文字小文字・ファイルとフォルダ）: {safe_location(other)} と {safe_location(path)}")
            seen[key] = (path, kind)


def collect(path, kind):
    """ZIPに入れるファイル {ZIP内の相対パス: (中身, 実行可能か)} と、除いたもの。"""
    files, left_out = {}, []
    if kind == "legacy-single":
        data = path.read_bytes()
        if not data.decode("utf-8").strip():
            raise Stop("RECIPE.md の本文が空です")
        files["RECIPE.md"] = (data, False)
        return files, left_out
    for item in sorted(path.rglob("*")):
        relative = item.relative_to(path)
        if any(part.startswith(".") or part in SKIP_NAMES for part in relative.parts):
            left_out.append((relative.as_posix(), "隠しファイル・生成物"))
            continue
        if linked(item):
            left_out.append((relative.as_posix(), "リンク"))
            continue
        if item.is_dir():
            continue
        if not regular(item):
            raise Stop(f"普通のファイルではないものがあります（パイプなど）。取り除いてから作ってください: {safe_location(relative.as_posix())}")
        windows_safe(relative.as_posix())
        if len(relative.parts) == 1 and relative.name in ADDED:
            raise Stop(f"レシピの直下に {relative.name} があり、入口と重なります。名前を変えてから作ってください")
        data = item.read_bytes()
        if kind == "os" and relative.as_posix() == "RECIPE.md":
            data = without_source(data.decode("utf-8")).encode("utf-8")
        files[relative.as_posix()] = (data, bool(item.stat().st_mode & stat.S_IXUSR))
    case_duplicates(files)
    required = {"os": ["RECIPE.md"], "legacy-package": ["recipe.json", "RECIPE.md"] if (path / "recipe.json").exists() else ["RECIPE.md"]}[kind]
    missing = [name for name in required if name not in files]
    if missing:
        raise Stop("レシピの本文がZIPに入りません: " + ", ".join(missing))
    body = files["RECIPE.md"][0].decode("utf-8", errors="replace") if "RECIPE.md" in files else ""
    if kind == "os":
        lines = body.splitlines()
        end = [line.strip() for line in lines].index("---", 1)  # 閉じ区切りの「行」
        body = "\n".join(lines[end + 1:])
    if "RECIPE.md" in files and not body.strip():
        raise Stop("RECIPE.md の本文が空です")
    return files, left_out


def describe(path, kind, files):
    text = files["RECIPE.md"][0].decode("utf-8") if "RECIPE.md" in files else ""
    if kind == "os":
        meta = strict_front_matter(text)
        return {"id": path.name, "title": meta.get("title") or path.name, "version": meta.get("version", "—"),
                "status": meta.get("status", "—"), "summary": meta.get("summary", ""), "format": "Builder OS"}
    if kind == "legacy-package" and "recipe.json" in files:
        meta = json.loads(files["recipe.json"][0].decode("utf-8"))
        return {"id": path.name, "title": meta.get("name") or path.name, "version": str(meta.get("version", "—")),
                "status": str(meta.get("status", "—")), "summary": meta.get("summary", ""), "format": "old Builder (v3)",
                "target": meta.get("target"), "ai": (meta.get("runtime") or {}).get("ai")}
    heading = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.stem)
    status = re.search(r"検証ステータス:\s*`?([a-z]+)", text)
    return {"id": path.stem if kind == "legacy-single" else path.name, "title": heading, "version": "—",
            "status": status[1] if status else "—", "summary": "", "format": "old Builder (v3)"}


def entry(info, missing=(), single=False, has_binaries=False):
    old = info["format"] != "Builder OS"
    lines = [
        f"# {info['title']}", "",
        "**AIへ / To the AI**: 同じフォルダの `REPRODUCE.md` を読み、短い設計を見せてOKを待ってください。読むための展開は先に行えます。 / "
        "Read `REPRODUCE.md`, show a short plan, and wait for OK before building. You may extract the ZIP to read it.", "",
        "## 使い方", "",
        "1. ZIPを Claude Code か Codex に渡し、「再現して。先に設計を見せて、OKを待って」と頼みます。",
        "2. AIが作るもの・保存先・仮の値・確認方法を短く見せます。よければ「OK」と返すだけです。",
        "3. AIが作成と可能な検証まで進め、開き方と未確認の点を報告します。細かな操作方法の指定は不要です。公開・費用など範囲が変わる操作は別途確認します。",
        "", "新しい空の作業フォルダにZIPだけを置いて始めると、元の完成品と混ざりません。依頼文もZIPと一緒に伝えてください。",
        "", "> 再現して。先に設計を見せて、OKを待って。",
        "", "## How to use", "",
        "1. Give the ZIP to Claude Code or Codex and say: Reproduce this. Show me the plan first and wait for my OK.",
        "2. Review the short plan, destination, proposed sample values and checks. Reply OK.",
        "3. The AI builds and runs available checks, then reports how to open the result and any gaps. It chooses routine local steps itself. Publishing, costs and other scope changes need specific authorization.",
        "", "Start in a new empty working folder with only the ZIP. Send this request with it:",
        "", "> Reproduce this. Show me the plan first and wait for my OK.",
        "", "## このレシピ / This recipe", "",
        f"- ID: `{info['id']}`",
        f"- 版 / Version: {info['version']}",
        f"- 状態 / Status: {info['status']}",
        f"- 形式 / Format: {info['format']}",
    ]
    if info.get("summary"):
        lines.append(f"- 概要 / Summary: {info['summary']}")
    if info.get("target") == "builder":
        lines.append("- 種類 / Kind: AIの環境に機能を足すレシピ / adds a capability to your AI environment"
                     + (f"（{info['ai']}）" if info.get("ai") else ""))
    if single:
        lines += ["", "旧ビルダーが本文から作る形のレシピで、テンプレートと試験は入っていません。AIは本文から書き起こします（元の検証済みのコードとは別物になりえます）。 / "
                  "This old-format recipe has no templates or tests; the AI writes the code from the text, so it may differ from the originally verified code."]
    if has_binaries:
        lines += ["", "画像などの素材が入っています。使える条件は、レシピ内の説明（TERMS.md など）に従ってください。 / "
                  "This ZIP includes images or other assets; follow the terms given inside the recipe (such as TERMS.md)."]
    if missing:
        lines += ["", "このZIPに入っていない参照 / Referenced but not included: " + ", ".join(f"`{name}`" for name in missing)
                  + "（AIは不足として扱い、一般の知識や現在の公式資料で補ったと伝える / the AI treats them as missing and says how it covers them）"]
    if old:
        lines += ["", "旧ビルダー形式の確認状態（verified など）は旧ビルダーでの記録で、この形での再現を保証しません。 / "
                  "Statuses such as `verified` are records from the old Builder; they do not promise this reproduction works."]
    elif info["status"] == "draft":
        lines += ["", "`draft` は、この版の再現と完成条件すべての確認がまだ完了していない下書きです。一部の試験結果は本文の記録を参照してください。 / "
                  "`draft` means reproduction and all completion checks for this version are not yet complete. See the recipe's record for any partial verification."]
    return ("\n".join(lines) + "\n").encode("utf-8")


def missing_references(files):
    """本文が参照しているのに ZIP に入っていないファイル（旧v3の knowledge/ など）。"""
    text = files["RECIPE.md"][0].decode("utf-8", errors="replace") if "RECIPE.md" in files else ""
    named = set(re.findall(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)", text)) | set(re.findall(r"(?<![\w/.-])(knowledge/[\w.-]+\.md)", text))
    out = []
    for name in sorted(named):
        if re.match(r"[a-z]+:", name):
            continue
        clean = re.sub(r"^\./", "", name)
        if clean not in files:
            out.append(name)
    return out


def findings(files):
    found = []
    for position, (name, (data, _)) in enumerate(sorted(files.items()), 1):
        location = safe_location(name, f"ファイル{position}（名前を伏せました）")
        for label in detected_kinds(name):
            found.append({"file": location, "line": None, "kind": label})
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for label in detected_kinds(line):
                found.append({"file": location, "line": number, "kind": label})
    return found


def assets(files):
    """素材らしいファイル（画像・音・動画・フォント・PDF、assets/ の中）。テキストの SVG も含む。"""
    return sorted(name for name in files if name.startswith("assets/") or Path(name).suffix.lower() in ASSET_SUFFIXES)


def binaries(files):
    out = []
    for name, (data, _) in sorted(files.items()):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            out.append(name)
    return out


def destination(argument):
    out = Path(argument)
    out = (out if out.is_absolute() else Path.cwd() / out).resolve()
    if out.suffix.lower() != ".zip":
        raise Stop("出力先は .zip で終わる名前にしてください")
    if out.exists():
        raise Stop("指定した出力先に同じ名前のファイルがあります。上書きしません")
    if not out.parent.is_dir():
        raise Stop("指定した出力先のフォルダがありません")
    recipes = (ROOT / "recipes").resolve()
    if out.parent == ROOT or out.parent == recipes or recipes in out.parents:
        raise Stop("ワークスペースの直下と recipes/ の中には出しません。デスクトップなどを指定してください")
    return out


def build(argument, out_argument, reviewed):
    path, kind = locate(argument)
    files, left_out = collect(path, kind)
    info = describe(path, kind, files)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", info["id"]):
        raise Stop("IDは英小文字・数字・ハイフンにしてください（指定したレシピの名前）")
    windows_safe(info["id"])
    case_duplicates([*files, *ADDED])
    missing = missing_references(files)
    binary_names, asset_names = binaries(files), assets(files)
    files["README.md"] = (entry(info, missing, single=kind == "legacy-single", has_binaries=bool(binary_names or asset_names)), False)
    files["REPRODUCE.md"] = (PROCEDURE.read_bytes(), False)
    found = findings(files)
    locations = {name: safe_location(name, f"ファイル{position}（名前を伏せました）")
                 for position, name in enumerate(sorted(files), 1)}
    report = {"id": safe_location(info["id"], "レシピ名（伏せました）"), "format": kind, "files": len(files),
              "left_out": [(safe_location(name, f"除外項目{n}（名前を伏せました）"), reason)
                           for n, (name, reason) in enumerate(left_out, 1)],
              "findings": found, "binaries": [locations[name] for name in binary_names],
              "assets": [locations[name] for name in asset_names],
              "missing_references": [safe_location(name, f"不足参照{n}（名前を伏せました）")
                                     for n, name in enumerate(missing, 1)], "zip": None}
    if reviewed:
        report["reviewed_notice"] = "--reviewed の一括解除は廃止しました。検出値の持ち出しを防ぐため、指定しても検査と停止を省きません。"
    out = destination(out_argument)
    if found:
        report["stopped"] = "秘密・絶対パス・メールの型が見つかりました。--reviewed でも解除できません。原本は変えず、了承された配布用の別候補で該当箇所を置換・削除し、再検査してください。"
        return report, 3
    with zipfile.ZipFile(out, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.comment = (f"Read {info['id']}/README.md and REPRODUCE.md. You may extract to read. "
                           "Show the plan and wait for OK before building. / AIへ: 読むための展開は可能。設計を見せてOKを待ってから作成する。").encode("utf-8")
        for name in sorted(files):
            data, executable = files[name]
            item = zipfile.ZipInfo(f"{info['id']}/{name}", FIXED_TIME)
            item.external_attr = ((0o755 if executable else 0o644) | stat.S_IFREG) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data)
    report["zip"] = safe_location(str(out), "指定した出力先（パスを伏せました）")
    return report, 0


def show(report):
    lines = [f"レシピ {report['id']}（{report['format']}）"]
    if report.get("zip"):
        lines.append(f"ZIPを作りました: {report['zip']}（{report['files']} ファイル）")
        lines.append("  ZIPと一緒に伝える依頼文: 再現して。先に設計を見せて、OKを待って。")
    for name, reason in report["left_out"]:
        lines.append(f"  入れなかったもの: {name}（{reason}）")
    for item in report["findings"]:
        position = item["line"] if item["line"] is not None else "名前"
        lines.append(f"  確かめること: {item['file']}:{position} {item['kind']}")
    for name in report.get("missing_references", []):
        lines.append(f"  ZIPに入っていない参照（入口に書きました）: {name}")
    if not report["findings"]:
        lines.append("  既知の型（キー・秘密鍵・一部の絶対パス・メール）には当たりませんでした。これだけで公開してよいとは判断できません。")
    if report["binaries"]:
        lines.append("  画像などテキスト以外（権利と、中の撮影場所・作者などの情報を確かめる）: " + ", ".join(report["binaries"]))
    if report.get("reviewed_notice"):
        lines.append(report["reviewed_notice"])
    if report.get("stopped"):
        lines.append("止めました: " + report["stopped"])
    lines.append("送信・公開はしていません。渡す前に、権利と個人情報を本人が確かめてください。")
    return "\n".join(lines)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = SafeArgumentParser(prog="recipe_zip.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("recipe")
    parser.add_argument("--out", required=True)
    parser.add_argument("--reviewed", action="store_true", help="旧コマンド互換のため解釈するが、検出の一括解除はしない")
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    try:
        report, code = build(arguments.recipe, arguments.out, arguments.reviewed)
    except Stop as error:
        print(f"止めました: {safe_location(str(error), '入力に問題があります（値は表示しません）')}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError):
        # OS・文字コード・JSON等の例外にはファイル名や値が含まれることがある。
        print("止めました: 入出力またはレシピの形式を確認してください（パス・値・例外本文は表示しません）", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2) if arguments.json else show(report))
    return code


if __name__ == "__main__":
    sys.exit(main())

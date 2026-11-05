#!/usr/bin/env python3
"""ワークスペースのレシピのメタ情報だけを読み、旧版と同じ列の一覧を返す。"""
import argparse
import html
import json
import os
from pathlib import Path
import re
import stat
import sys
import unicodedata
from urllib.parse import quote


MAX_METADATA = 1024 * 1024
FIELDS = {"製品名": "name", "用途分類": "usecase", "検証ステータス": "status",
          "動作確認": "tested", "配布元検証": "signoff"}
# 旧形式とOS形式で状態の語を分け、旧verifiedをOSのconfirmedと混ぜない
STATES = {"legacy": {"verified": "✅", "experimental": "🧪", "skeleton": "🚧"},
          "os": {"draft": "📝", "confirmed": "✅"}}
TESTED = {"pass": "✅", "untested": "⬜", "na": "➖", "n/a": "➖"}
LISTED = ("title", "name", "id", "summary", "status", "target", "recipe_kind", "usecase", "superseded_by")
INVISIBLE = re.compile("[‎‏‪-‮⁦-⁩]")


def redirected(path):
    info = os.lstat(path)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def path_state(path):
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("リンク・再解析ポイントは読みません")
    return info


def read_metadata(path):
    before = path_state(path)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_METADATA:
        raise ValueError("通常のメタ情報ファイルではありません")
    parents = [(parent, path_state(parent)) for parent in path.parents] if os.name == "nt" else []
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_METADATA
                or not info.st_ino or not os.path.samestat(before, info) or not os.path.samestat(info, path_state(path))
                or any(not os.path.samestat(state, path_state(parent)) for parent, state in parents)):
            raise ValueError("通常のメタ情報ファイルではありません")
        content = stream.read(MAX_METADATA + 1)
    if len(content) > MAX_METADATA:
        raise ValueError("メタ情報が大きすぎます")
    if b"\0" in content:
        raise ValueError("バイナリは読みません")
    text = content.decode("utf-8-sig")
    if not text.strip():
        raise ValueError("空のファイルです")
    return text


def unique_object(pairs):
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("同じ項目が重複しています")
    return dict(pairs)


def scalar(value):
    value = value.strip()
    if value.startswith('"'):
        return json.loads(value)
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value.split(" #", 1)[0].strip()


def markdown_metadata(text):
    lines = text.splitlines()
    if lines and lines[0].rstrip() == "---":
        ending = [line.rstrip() for line in lines].index("---", 1)
        metadata = {}
        for line in lines[1:ending]:
            match = re.fullmatch(r"([a-z_]+):\s*(.*)", line)
            if match:
                value = scalar(match[2])
                if value in {"|", ">", "|-", ">-"}:
                    raise ValueError("一覧用のメタ情報は1行で記入してください")
                if match[1] in metadata and match[1] in LISTED:
                    raise ValueError("一覧用のメタ情報が重複しています")
                metadata[match[1]] = value
        metadata.pop("tested", None)
        metadata.pop("signoff", None)
        return {**metadata, "name": metadata.get("title"), "format": "os"}
    metadata = {"format": "legacy"}
    heading = None
    for line in lines:
        if line.startswith("# ") and heading is None:
            heading = line[2:].removeprefix("レシピ: ").strip()
        elif heading is not None and line.strip() and "summary" not in metadata and not line.startswith(("#", "-", "<!--")):
            metadata["summary"] = line.strip()
        match = re.match(r"^- (製品名|用途分類|検証ステータス|動作確認|配布元検証):\s*(.*)", line)
        if match:
            metadata.setdefault(FIELDS[match[1]], match[2])
    metadata.setdefault("name", heading)
    state = re.match(r"`?(verified|experimental|skeleton)\b", metadata.get("status", ""))
    metadata["status"] = state[1] if state else ""
    tested = metadata.get("tested", "")
    metadata["tested"] = {platform: match[1] if (match := re.search(platform + r"\s*([✅⬜➖])", tested, re.I)) else "—"
                          for platform in ("mac", "win")}
    metadata["signoff"] = "✅" if "✅" in metadata.get("signoff", "") else "—"
    return metadata


def catalog(root):
    root = Path(root)
    recipes = root / "recipes"
    entries, warnings = [], []
    if recipes.exists() and redirected(recipes) or recipes.is_symlink():
        return [], ["recipes: リンクの置き場は読みません"]
    if not recipes.exists():
        return [], []
    def unreadable(error):
        try:
            place = Path(error.filename).relative_to(root).as_posix()
        except (TypeError, ValueError):
            place = "recipes"
        warnings.append(f"{place}: フォルダを読めないため一覧から除外しました")
    for directory, folders, names in os.walk(recipes, onerror=unreadable, followlinks=False):
        parent = Path(directory)
        for name in sorted(folders + names):
            path = parent / name
            if redirected(path):
                warnings.append(f"{path.relative_to(root).as_posix()}: リンクは読みません")
        folders[:] = sorted(name for name in folders if not name.startswith(".")
                            and name not in {"node_modules", "__pycache__"} and not redirected(parent / name))
        package = "recipe.json" in names or "RECIPE.md" in names
        if package and parent == recipes:
            package = False
            warnings.append("recipes: 直下の recipe.json・RECIPE.md はパッケージとして読みません")
            names = [name for name in names if name not in {"recipe.json", "RECIPE.md"}]
        if package:
            folders[:] = []
            candidates = ["recipe.json" if "recipe.json" in names else "RECIPE.md"]
        else:
            candidates = sorted(name for name in names if name.endswith(".md")
                                and name.lower() != "readme.md" and not name.startswith("."))
        for name in candidates:
            path = parent / name
            if redirected(path):
                continue
            relative = path.relative_to(root).as_posix()
            try:
                text = read_metadata(path)
                if name == "recipe.json":
                    metadata = json.loads(text, object_pairs_hook=unique_object)
                    if isinstance(metadata, dict):
                        metadata["format"] = "legacy"
                else:
                    metadata = markdown_metadata(text)
                if not isinstance(metadata, dict):
                    raise ValueError("メタ情報がオブジェクトではありません")
                for field in LISTED:
                    if field in metadata and metadata[field] is not None and not isinstance(metadata[field], str):
                        raise ValueError("一覧用の文字列が不正です")
                tested = metadata.get("tested", {})
                if not isinstance(tested, dict) or any(not isinstance(value, str) for value in tested.values()):
                    raise ValueError("動作確認の形式が不正です")
                recipe_id = parent.name if package else path.stem
                if metadata.get("id") and metadata["id"] != recipe_id:
                    warnings.append(f"{relative}: メタ情報のIDと保存名が異なります。保存名で表示します")
                category = parent.parent.relative_to(recipes) if package else parent.relative_to(recipes)
                target = (parent / "RECIPE.md") if package else path
                body = os.lstat(target)
                if not stat.S_ISREG(body.st_mode) or body.st_size == 0:
                    raise ValueError("レシピ本文がありません")
                entries.append({**metadata, "id": recipe_id,
                                "category": category.as_posix() if category.parts else "—",
                                "path": target.relative_to(root).as_posix()})
            except (OSError, ValueError, UnicodeError, TypeError, RecursionError):
                warnings.append(f"{relative}: メタ情報を確認できないため一覧から除外しました")
    def order(entry):
        category = entry["category"]
        priority = 0 if category == "official" or category.startswith("official/") else 2 if category == "—" else 1
        return priority, category, entry["id"], entry["path"]
    entries.sort(key=order)
    key = lambda recipe_id: unicodedata.normalize("NFC", recipe_id).casefold()
    for recipe_id in sorted({key(entry["id"]) for entry in entries}):
        same = sorted({entry["id"] for entry in entries if key(entry["id"]) == recipe_id})
        if sum(key(entry["id"]) == recipe_id for entry in entries) > 1:
            warnings.append(f"ID重複: {'・'.join(same)}。番号だけで決めず、製品名とリンク先を本人に確認してください")
    return entries, warnings


def cell(value, limit=100):
    text = "".join(" " if unicodedata.category(char) == "Cc" else char
                   for char in INVISIBLE.sub("", str(value if value is not None else "—")))
    text = " ".join(text.split()) or "—"
    if len(text) > limit:
        text = text[:limit - 1] + "…"
    text = html.escape(text, quote=False)
    return re.sub(r"([\\`*_|\[\]])", r"\\\1", text)


def table(entries, warnings):
    if not entries:
        lines = ["このワークスペースには、一覧に表示できるレシピがまだありません。",
                 "配布されたレシピを recipes/ に置いて「レシピ一覧見せて」と頼んでください。"]
    else:
        lines = [f"📦 在庫レシピ {len(entries)} 件 ──「これ作って」で設計の相談を始められます。", "",
                 "| # | 製品名 | ID | カテゴリ | 概要 | 用途 | 状態 | Mac | Win | 検証 |",
                 "|---:|---|---|---|---|---|---|---|---|---|"]
        for number, entry in enumerate(entries, 1):
            tested = entry.get("tested", {})
            tested = tested if isinstance(tested, dict) else {}
            platforms = [TESTED.get(tested.get(platform), tested.get(platform) if tested.get(platform) in {"✅", "⬜", "➖"} else "—")
                         for platform in ("mac", "win")]
            signoff = entry.get("signoff")
            verified = "✅" if isinstance(signoff, dict) and signoff.get("date") else "✅" if signoff == "✅" else "—"
            usecase = "🧩 ワークスペースに追加" if entry.get("target") == "builder" else "判断・選定" if entry.get("recipe_kind") == "decision" else entry.get("usecase", "制作")
            if str(entry.get("superseded_by") or "").startswith("tools/skills/"):
                usecase = "OSの初期スキルに統合（導入しない）"
            title = ("📦 " if entry["format"] == "legacy" and entry["path"].endswith(("/RECIPE.md", "/recipe.json")) else "📄 ") + cell(entry.get("name"), 60)
            values = [str(number), f"[{title}]({quote(entry['path'], safe='/')})", cell(entry["id"]),
                      cell(entry["category"]), cell(entry.get("summary")), cell(usecase),
                      STATES.get(entry["format"], {}).get(str(entry.get("status")), "—"), *platforms, verified]
            lines.append("| " + " | ".join(values) + " |")
        lines += ["", "➡「番号で作って」「製品名・IDで作って」で選べます。設計を見せて、OKをもらってから作ります。",
                  "形の印: 📦=旧形式のパッケージ、📄=単体MarkdownまたはOS形式。形の印だけでは旧/新や確認状態を判断しません。付属10件はすべて旧形式です。",
                  "凡例: ✅=記録上の確認済み、⬜=未検証（動かない確証ではありません）、➖=対象外、—=記録なし、📝=下書き、🧪=試作、🚧=骨組み。",
                  "旧形式の状態・Mac・Win・検証は旧ビルダーでの記録です。現OSでの再制作や今回の動作を確認した印ではありません。OS形式の✅はconfirmed（レシピに記した条件内で確認済み）です。"]
    merged = [entry for entry in entries if str(entry.get("superseded_by") or "").startswith("tools/skills/")]
    if merged:
        lines += ["統合済み: " + "、".join(f"{cell(entry['id'])} → `{cell(entry['superseded_by'])}`" for entry in merged)
                  + "。過去の記録として読めますが、レシピとしては導入しません。OSの初期スキルを使います。"]
    if warnings:
        lines += ["", "注意（一覧は未確認項目を含みます）:", *("- " + cell(warning, 300) for warning in warnings)]
    return "\n".join(lines) + "\n"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="試験・照合用のメタ情報を返す")
    arguments = parser.parse_args()
    entries, warnings = catalog(Path(__file__).resolve().parents[1])
    if arguments.json:
        print(json.dumps({"recipes": entries, "warnings": warnings}, ensure_ascii=False, indent=2))
    else:
        print(table(entries, warnings), end="")


if __name__ == "__main__":
    main()

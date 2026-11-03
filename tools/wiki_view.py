#!/usr/bin/env python3
"""Wiki をグラフと画面で見る・Sveltia CMS で直すための小さなサーバー（python の標準だけ。どの AI からでも動く）。

使い方（ワークスペースのいちばん上で）:
  python3 tools/wiki_view.py open [view|graph|3d|edit]   裏でサーバーを起動して（動いていればそれを使い）、ブラウザで開く
        view = ページの一覧と本文 / graph = 2D のグラフ / 3d = 3D のグラフ / edit = Sveltia CMS（Chrome か Edge）
        --no-browser でブラウザを開かず、URL だけを出す（環境変数 WIKI_VIEW_NO_BROWSER=1 でも同じ。試験用）
  python3 tools/wiki_view.py stop                         裏のサーバーを止める
  python3 tools/wiki_view.py serve [--port N]             前でサーバーを動かす（止めるまで）
  python3 tools/wiki_view.py json                         index.json を出すだけ（確かめ用）
  python3 tools/wiki_view.py diagnose [--root ワークスペース]       関係の読取専用診断を JSON で出す（修復・保存はしない）
  python3 tools/wiki_view.py audit [--root ワークスペース]          Markdownの入口不足を点検する（指摘ありは終了コード1。保存しない）
        --migration-completion で移行完了時のコピー先・生成案内・状態も確認（孤立・日付差は参考情報）。後日の通常点検では指定しない。

- 本人のデータ（wiki/・recipes/）は読むだけ。このサーバーは何も書かない。直すのは Sveltia（ブラウザがワークスペースのファイルに直接書く）で、
  commit はしない（Sveltia の設定の「ローカルの変更を commit する」が OFF＝既定のとき。次に AI と話すとき、wiki/README.md の「保存前の安全確認」に従い、保存が必要なときに中身を見て commit する）。
- 点 = ページ（wiki/ の Markdown。知識配下はファイル名だけで目次と判定しない）と、レシピ（recipes/ の RECIPE.md と v3 の1ファイルのレシピ）。
- 線 = (1) 本文の中の相対リンク（[..](../notes/x.md) など）(2) v3 から移したカードの related:（v3 の「種類/名前」）
  (3) 案件ページの recipe: <id>@<版> → そのレシピ。案件の path:（成果物の場所）はページではないので線にしない。
- 大きさ = つながりの数（ほかのページから参照された数を重く数える）。色 = 種類。進行中の案件は光輪、一時停止は暗く、未確認（draft）は少し薄く。
- 配るのは画面（tools/wiki-view/）と index.json だけ。127.0.0.1 だけで待ち受け、Host・Origin が手元でなければ断る。
- 画面で動いてよいスクリプトは、画面に書いてあるものと、画面が中身を固定した（integrity）CDN のファイルだけ（CSP。csp() を見る）。
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import posixpath
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

for _s in (sys.stdout, sys.stderr):  # Windows のコンソールでも落ちない
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
UI = HERE / "wiki-view"
PORT = 8330
COLLECTIONS = [("projects", "案件"), ("notes", "知識"), ("v3", "v3 から移した知識"), ("recipes", "レシピ"), ("me", "わたし"), ("other", "そのほか")]
KINDS = {"knowledge": "一般知識", "decisions": "判断", "troubleshooting": "トラブル対処", "patterns": "使えた型", "sources": "資料", "stacks": "技術"}
SKIP_NAMES = {"README.md", "index.md"}
STATIC = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
          ".yml": "application/yaml; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}
SCRIPT_OR_COMMENT = re.compile(rb"<!--|<script\b([^>]*)>", re.I)


def scripts(html):
    """HTML の <script> 要素の（属性, 中身）。ブラウザと同じく、コメントの中の <script> は数えず、<script> の中の <!-- はコメントにしない。"""
    out, i, low = [], 0, html.lower()
    while (m := SCRIPT_OR_COMMENT.search(html, i)):
        if m.group(0) == b"<!--":
            j = html.find(b"-->", m.end())
            i = len(html) if j < 0 else j + 3
            continue
        j = low.find(b"</script", m.end())
        j = len(html) if j < 0 else j
        out.append((m.group(1), html[m.end():j]))
        i = j
    return out


def attr(attrs, name):
    m = re.search(rb"\b" + name + rb"""\s*=\s*(?:"([^"]*)"|'([^']*)')""", attrs, re.I)
    return (m.group(1) if m.group(1) is not None else m.group(2)).decode() if m else None


def csp(html):
    """画面（html）に付ける CSP。動いてよいスクリプトは、画面に書いてあるもの（中身のハッシュ）と、画面が中身を固定した（integrity）
    CDN のファイル（URL そのもの）だけ。Sveltia が機能によってあとから読む別の部品など、固定していないものはブラウザが読み込まない。
    javascript: のリンクや、本文に紛れ込んだスクリプトも動かない。（CSP は URL を許すだけなので、読むファイルには必ず integrity を付ける）"""
    src, urls = [], set()
    for attrs, body in scripts(html):
        url = attr(attrs, b"src")
        if url is not None:
            if url.startswith("https://") and (attr(attrs, b"integrity") or "").startswith("sha384-"):
                urls.add(url)
            continue
        src.append(f"'sha256-{base64.b64encode(hashlib.sha256(body).digest()).decode()}'")
        if (attr(attrs, b"type") or "").lower() == "importmap":
            try:
                pins = json.loads(body).get("integrity", {})
            except (ValueError, AttributeError):
                pins = {}
            urls |= {u for u, h in pins.items() if isinstance(u, str) and u.startswith("https://") and str(h).startswith("sha384-")}
    src += sorted(urls)
    return f"script-src {' '.join(src) or chr(39) + 'none' + chr(39)}; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"


# ---------------------------------------------------------------- ページを読む
def front_matter(text):
    """先頭の --- で囲んだ部分を、ゆるく読む（YAML の一部だけ。読めない形は文字のまま）。→ (dict, 本文)"""
    m = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not m:
        return {}, text
    fm, key = {}, None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s*(.*)$", line)
        if item and key is not None:
            if not isinstance(fm.get(key), list):
                fm[key] = []
            fm[key].append(scalar(item.group(1)))
            continue
        kv = re.match(r"^([A-Za-z0-9_.\-]+):(?:\s+(.*))?$", line)
        if kv:
            key, val = kv.group(1), (kv.group(2) or "").strip()
            if val.startswith("[") and val.endswith("]"):
                try:
                    fm[key] = json.loads(val)
                except ValueError:
                    fm[key] = [scalar(x) for x in val[1:-1].split(",") if x.strip()]
            else:
                fm[key] = scalar(val) if val else ""
        elif key is not None and line.startswith((" ", "\t")):  # 入れ子や折り返しは文字のままつなぐ
            prev = fm.get(key)
            fm[key] = ((" ".join(prev) if isinstance(prev, list) else prev or "") + " " + line.strip()).strip()
    return fm, text[m.end():]


def scalar(v):
    v = v.strip()
    if v.startswith('"'):
        try:
            return json.loads(v)
        except ValueError:
            pass
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return re.sub(r"\s+#.*$", "", v).strip()  # 行の終わりのコメント（status: draft  # draft / confirmed）


def first_line(body):
    for line in body.splitlines():
        s = line.strip()
        if s and not s.startswith(("#", "|", "```", "<!--", "---")):
            s = re.sub(r"^[-*]\s+|^\d+\.\s+", "", s)
            return (s[:117] + "…") if len(s) > 118 else s
    return ""


def safe_files(root, base, pattern):
    """base の下で pattern に合う普通のファイル（. で始まる場所・node_modules・リンク・ハードリンク・外を指すものは除く）。"""
    out = []
    real_base = os.path.realpath(base)
    for p in sorted(Path(base).rglob(pattern)) if Path(base).is_dir() else []:
        rel = p.relative_to(root)
        if any(part.startswith(".") or part.casefold() == "node_modules" for part in rel.parts):
            continue
        if p.is_symlink() or not p.is_file() or any(q.is_symlink() for q in p.parents if root in q.parents or q == root):
            continue
        real = os.path.realpath(p)
        if not real.startswith(real_base + os.sep) or os.stat(real).st_nlink != 1:
            continue
        out.append(p)
    return out


def collection_of(rel):
    parts = rel.split("/")
    if parts[0] == "recipes":
        return "recipes"
    if len(parts) >= 3 and parts[1] in ("projects", "me") and len(parts) == 3:
        return parts[1]
    if len(parts) >= 4 and parts[1] == "notes" and parts[2] == "v3":
        return "v3"
    if parts[1] == "notes":
        return "notes"
    return "other"


def edit_target(col, rel):
    """Sveltia（tools/wiki-view/admin/config.yml）のどのコレクションの、どの項目で直せるか。直せないものは None。"""
    parts = rel[:-3].split("/")
    if col in ("projects", "notes") and len(rel.split("/")) == 3:
        return {"collection": col, "slug": parts[-1]}
    if col == "me" and parts[-1] in ("profile", "proposals"):
        return {"collection": "me", "slug": parts[-1]}
    return None


def local_reference(value):
    value = str(value)
    decoded = unquote(value)
    if not value or decoded.startswith(("/", "~")) or "?" in value or re.search(r"[\x00-\x1f\x7f-\x9f\\|]", decoded) or re.match(r"^[a-z][a-z0-9+.-]*:", decoded, re.I):
        return None
    return value


def excluded_page(root, target):
    relative = Path(target)
    if relative.suffix != ".md" or relative.name == "README.md" or any(part.startswith(".") or part.casefold() == "node_modules" for part in relative.parts):
        return True
    try:
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return True
        info = current.lstat()
        return not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
    except FileNotFoundError:
        return False
    except OSError:
        return True


def page_context(page):
    relative = page["path"]
    migrated = page["collection"] == "v3"
    role = "notes" if migrated else page["collection"]
    subtype = relative.split("/")[3] if migrated and len(relative.split("/")) > 4 else "knowledge"
    subtype = "stacks" if subtype == "stack-knowledge" else subtype
    kind = (subtype if migrated else str(page["fm"].get("kind") or "knowledge")) if role == "notes" else ""
    if role == "notes" and kind not in KINDS:
        kind = "knowledge"
    return {"role": role, "origin": "v3" if migrated else "workspace", "kind": kind,
            "kind_label": KINDS.get(kind, ""), "previous_status": str(page["fm"].get("v3_status") or "") if migrated else "",
            "navigation": relative.startswith("wiki/notes/topics/") or relative in ("wiki/notes/index.md", "wiki/notes/v3/index.md", "wiki/notes/v3-migration.md", "wiki/notes/v3/recipes.md")}


def topic_id(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value) is not None


def classify_topics(pages):
    topics = {}
    for page in pages:
        fields = page["fm"]
        identifier = fields.get("os_topic_id")
        aliases = fields.get("aliases", [])
        if (topic_id(identifier) and page["path"] == f"wiki/notes/topics/{identifier}.md"
                and isinstance(fields.get("scope"), str) and fields["scope"].strip()
                and isinstance(fields.get("title"), str) and fields["title"].strip()
                and isinstance(aliases, list) and all(isinstance(alias, str) for alias in aliases)):
            topics[identifier] = {"id": identifier, "title": fields["title"], "scope": fields["scope"],
                                  "aliases": aliases, "key": page["key"], "count": 0}
    counts = {"pages": 0, "classified": 0, "pending": 0, "none": 0, "memberships": 0}
    for page in pages:
        fields = page["fm"]
        page.update(os_topics=[], os_topic_state="", topic_issues=[])
        if page["role"] != "notes" or page["navigation"]:
            continue
        counts["pages"] += 1
        identifiers = fields.get("os_topics", [])
        state = fields.get("os_topic_state", "")
        untouched = "os_topics" not in fields and "os_topic_state" not in fields
        valid = (isinstance(identifiers, list) and all(topic_id(identifier) and identifier in topics for identifier in identifiers)
                 and len(set(identifiers)) == len(identifiers))
        if untouched:
            counts["none"] += 1
            continue
        if state == "classified" and valid and identifiers:
            page.update(os_topics=identifiers[:], os_topic_state="classified")
            counts["classified"] += 1
            counts["memberships"] += len(identifiers)
            for identifier in identifiers:
                topics[identifier]["count"] += 1
        else:
            page["os_topic_state"] = "pending"
            counts["pending"] += 1
            if not valid:
                page["topic_issues"].append("カテゴリID配列が不正、重複、または未定義")
            if state not in ("classified", "pending"):
                page["topic_issues"].append("分類状態が未指定または不正")
            if state == "classified" and not identifiers:
                page["topic_issues"].append("割当済みだが有効な所属がない")
    return sorted(topics.values(), key=lambda topic: topic["id"]), counts


def resolve_references(root, pages, navigation):
    by_path = {page["path"]: page for page in pages + navigation}
    by_key = {page["key"]: page for page in pages + navigation}
    aliases, recipes = {}, {}
    archived = None
    for page in pages + navigation:
        if page["collection"] == "recipes":
            recipes.setdefault(page["id"], set()).add(page["key"])
        if page["origin"] != "v3" and page["collection"] != "projects":
            continue
        values = {page["id"]}
        if page["origin"] == "v3":
            suffix = page["path"][len("wiki/notes/v3/"):]
            values.update((suffix, suffix.removesuffix(".md"), "wiki/" + suffix))
        source = str(page["fm"].get("source") or "")
        if source.startswith("v3 "):
            original = local_reference(source[3:])
            if original:
                values.update((original, original.removesuffix(".md")))
        project_path = local_reference(page["fm"].get("v3_path", ""))
        if page["collection"] == "projects" and project_path and project_path.startswith("output/"):
            values.update((project_path.rstrip("/"), posixpath.basename(project_path.rstrip("/"))))
        for value in values:
            aliases.setdefault(value, set()).add(page["key"])

    references = []
    for page in pages + navigation:
        page["related"], page["navigation_related"] = [], []
        raw = [("body", href) for href in navigation_links(page.pop("_body_for_links"))]
        if page["origin"] == "v3":
            related = page["fm"].get("related", [])
            raw += [("related", value) for value in (related if isinstance(related, list) else [related]) if value]
        if page["collection"] == "projects" and page["fm"].get("recipe"):
            raw.append(("recipe", str(page["fm"]["recipe"]).split("@", 1)[0].strip()))
        if page["origin"] == "v3" and page["fm"].get("project"):
            raw.append(("project", str(page["fm"]["project"])))
        for relation, original in raw:
            value = local_reference(original)
            if relation == "body" and re.match(r"^(https?|mailto):", str(original), re.I):
                continue
            report = {"source": page["key"], "relation": relation, "reference": value or "（非対応の参照値）", "status": "unsupported"}
            hits, archive_paths = set(), set()
            if value:
                path, _, fragment = value.partition("#")
                path = unquote(path)
                if relation == "body":
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(page["path"]), path)) if path else page["path"]
                    if target.startswith(("wiki/", "recipes/")):
                        report["status"] = "not_page" if excluded_page(root, target) else "missing"
                        if target in by_path:
                            hits.add(by_path[target]["key"])
                        if target.startswith("wiki/notes/v3/"):
                            archive_paths.add("wiki/" + target[len("wiki/notes/v3/"):])
                    else:
                        report["status"] = "not_page"
                elif not path.startswith("..") and ".." not in path.split("/") and "?" not in path:
                    report["status"] = "missing"
                    if relation == "recipe":
                        hits.update(recipes.get(path, set()))
                    else:
                        exact = by_path.get("wiki/notes/v3/" + path.removesuffix(".md") + ".md")
                        hits.update({exact["key"]} if exact and relation == "related" else aliases.get(path, set()))
                        if relation == "project":
                            hits = {key for key in hits if by_key[key]["collection"] == "projects"}
                        archive_paths.update((path, path + ".md", "wiki/" + path.removesuffix(".md") + ".md"))
                if len(hits) > 1:
                    report["status"] = "ambiguous"
                elif len(hits) == 1:
                    target_page = by_key[next(iter(hits))]
                    report.update(status="resolved", target=target_page["key"], fragment="unchecked" if fragment else "none")
                    route = page["navigation"] or target_page["navigation"] or target_page in navigation
                    report["edge_type"] = "navigation" if route else "reference"
                    if target_page["key"] != page["key"]:
                        page["navigation_related" if route else "related"].append(target_page["key"])
                elif report["status"] == "missing" and archive_paths:
                    if archived is None:
                        archived = {path.relative_to(root / "imports/v3").as_posix() for path in safe_files(root, root / "imports/v3", "*.md")}
                    if archived.intersection(archive_paths):
                        report["status"] = "not_migrated"
            references.append(report)
        page["related"] = sorted(set(page["related"]))
        page["navigation_related"] = sorted(set(page["navigation_related"]))
    return references


def build_index(root):
    root = Path(root).resolve()
    pages, navigation = [], []
    for p in safe_files(root, root / "wiki", "*.md"):
        rel = p.relative_to(root).as_posix()
        if p.name in SKIP_NAMES and (not rel.startswith("wiki/notes/") or rel == "wiki/notes/index.md"):
            if p.name == "index.md":
                entry = read_page(root, p, rel, collection_of(rel))
                entry.update(page_context(entry))
                entry["navigation"] = True
                navigation.append(entry)
            continue
        pages.append(read_page(root, p, rel, collection_of(rel)))
    recipe_root = root / "recipes"
    recipe_files = []
    for path in safe_files(root, recipe_root, "*.md"):
        if path.name.lower() == "readme.md":
            continue
        packages = [parent for parent in path.parents if recipe_root in parent.parents
                    and ((parent / "recipe.json").exists() or (parent / "RECIPE.md").exists())]
        if packages:
            if path.name == "RECIPE.md" and len(packages) == 1 and packages[0] == path.parent:
                recipe_files.append(path)
        elif path.name != "RECIPE.md":
            recipe_files.append(path)
    for p in recipe_files:
        rel = p.relative_to(root).as_posix()
        pages.append(read_page(root, p, rel, "recipes"))
    for entry in pages:
        entry.update(page_context(entry))
    topics, topic_counts = classify_topics(pages)
    references = resolve_references(root, pages, navigation)
    by_key = {page["key"]: page for page in pages}
    topic_keys = {topic["id"]: topic["key"] for topic in topics}
    for entry in pages:
        for identifier in entry["os_topics"]:
            key = topic_keys[identifier]
            entry["navigation_related"].append(key)
            by_key[key]["navigation_related"].append(entry["key"])
    for entry in pages:
        entry["navigation_related"] = sorted(set(entry["navigation_related"]))
    back = {}
    for e in pages:
        for k in e["related"]:
            back[k] = back.get(k, 0) + 1
    for e in pages:
        e["backlinks"] = back.get(e["key"], 0)
        e["importance"] = min(100, 12 * e["backlinks"] + 4 * len(e["related"]))
        e["important"] = e["collection"] == "projects" and e["status"] == "active"
    present = {e["collection"] for e in pages}
    roles = {entry["role"] for entry in pages}
    counts = {status: sum(ref["status"] == status for ref in references) for status in ("resolved", "missing", "ambiguous", "not_migrated", "unsupported", "not_page")}
    return {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "root_name": root.name,
            "collections": [{"name": n, "label": l} for n, l in COLLECTIONS if n in present],
            "display_collections": [{"name": name, "label": label} for name, label in COLLECTIONS if name in roles],
            "reference_policy": "reference-only-v2",
            "topics": topics, "topic_counts": topic_counts,
            "diagnostics": {"counts": counts, "references": references, "read_only": True, "fragment_check": "not_performed"},
            "cards": len(pages), "card_nudge": 2000, "card_max": 3000, "pages": pages}


def view_index(root):
    data = build_index(root)
    data["diagnostics"].pop("references", None)
    return data


def markdown_destination(text, offset):
    start = offset
    angle = offset < len(text) and text[offset] == "<"
    if angle:
        offset += 1
        start = offset
    depth = 0
    while offset < len(text):
        character = text[offset]
        if character == "\\" and offset + 1 < len(text):
            offset += 2
            continue
        if angle and character == ">":
            return text[start:offset], offset + 1
        if not angle:
            if character.isspace() or character == ")" and depth == 0:
                return text[start:offset], offset
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
        if character == "\n":
            return None, offset
        offset += 1
    return (None if angle or depth else text[start:offset]), offset


def navigation_links(body):
    lines, fence, list_indent = [], None, None
    for line in body.splitlines():
        line = re.sub(r"^(?: {0,3}>[ \t]?)+", "", line)
        item = re.match(r"^( *)(?:[-+*]|[0-9]+[.)])[ \t]+", line)
        indentation = len(line) - len(line.lstrip(" "))
        if item and (list_indent is not None or indentation < 4):
            list_indent = item.end()
            content = line[item.end():]
        elif list_indent is not None and indentation >= list_indent:
            content = line[list_indent:]
        else:
            content = line
        content = re.sub(r"^(?: {0,3}>[ \t]?)+", "", content)
        if fence:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*", content):
                fence = None
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", content)
        if opening and (opening[1][0] != "`" or "`" not in opening[2]):
            fence = opening[1]
        else:
            item = re.match(r"^( *)(?:[-+*]|[0-9]+[.)])[ \t]+", line)
            indentation = len(line) - len(line.lstrip(" "))
            if item:
                if list_indent is None and indentation >= 4:
                    continue
                list_indent = item.end()
            elif line.strip():
                if indentation >= (list_indent or 0) + 4 or line.startswith("\t"):
                    continue
                if list_indent is not None and indentation < list_indent:
                    list_indent = None
            lines.append(line)
    body = "\n".join(lines)
    body = re.sub(r"(?<!`)(`+)(?!`)(.*?)(?<!`)\1(?!`)", "", body, flags=re.S)
    body = re.sub(r"<!--.*?(?:-->|$)", "", body, flags=re.S)
    body = re.sub(r"<(pre|code|script|style|textarea)\b[^>]*>.*?(?:</\1\s*>|\Z)", "", body, flags=re.I | re.S)
    body = re.sub(r"!\[([^\]]*)\]\([^)]*\)", lambda match: match[1], body)
    definitions = {}
    for definition in re.finditer(r"^ {0,3}\[([^\]]+)\]:[ \t]*", body, re.M):
        value, _ = markdown_destination(body, definition.end())
        if value:
            definitions.setdefault(" ".join(definition[1].split()).casefold(), value)
    body = re.sub(r"^ {0,3}\[[^\]]+\]:[^\n]*$", "", body, flags=re.M)
    links, consumed = [], 0
    for label in re.finditer(r"\[([^\]\n]*)\]", body):
        if label.start() < consumed:
            continue
        before = body[:label.start()]
        if (len(before) - len(before.rstrip("\\"))) % 2:
            continue
        image = before.endswith("!") and (len(before[:-1]) - len(before[:-1].rstrip("\\"))) % 2 == 0
        offset = label.end()
        target = None
        if offset < len(body) and body[offset] == "(":
            offset += 1
            while offset < len(body) and body[offset].isspace():
                offset += 1
            target, offset = markdown_destination(body, offset)
            tail = re.match(r'''\s*(?:"[^"\n]*"|'[^'\n]*'|\([^\)\n]*\))?\s*\)''', body[offset:])
            if target is None or not tail:
                continue
            consumed = offset + tail.end()
        else:
            reference = re.match(r"\[([^\]\n]*)\]", body[offset:])
            name = (reference[1] or label[1]) if reference else label[1]
            target = definitions.get(" ".join(name.split()).casefold())
            consumed = offset + reference.end() if reference else offset
        if target and not image:
            links.append(re.sub(r"\\([\\()<> ])", r"\1", target))
    return links


def audit_navigation(root):
    root = Path(root).resolve()
    entry = "wiki/index.md"
    required = ("wiki/README.md", "wiki/me/profile.md", "wiki/me/proposals.md",
                "wiki/projects/index.md", "wiki/notes/index.md", "tools/recipes.md")
    paths = safe_files(root, root / "wiki", "*.md")
    for directory, name in (("tools", "recipes.md"), ("recipes", "README.md")):
        paths += [path for path in safe_files(root, root / directory, name) if path.parent == root / directory]
    pages, edges, findings = {}, {}, []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            pages[relative] = front_matter(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            findings.append(dict(code="unreadable_page", page=relative))
    for relative, (_, body) in pages.items():
        edges[relative] = set()
        for original in navigation_links(body):
            if re.match(r"^[a-z][a-z0-9+.-]*:", original, re.I):
                continue
            value = local_reference(original)
            if not value:
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(relative), unquote(value.split("#", 1)[0])))
            if value.startswith("#"):
                target = relative
            if not target.startswith(("wiki/", "recipes/", "tools/")) or not target.endswith(".md"):
                continue
            if target in pages:
                edges[relative].add(target)
            elif relative.startswith("wiki/") and (target.startswith("wiki/") or target in required or target == "recipes/README.md"):
                findings.append(dict(code="missing_link", page=relative, target=target))
    reached, pending = set(), [entry] if entry in pages else []
    while pending:
        current = pending.pop()
        if current not in reached:
            reached.add(current)
            pending.extend(edges.get(current, set()) - reached)
    for target in (entry, *required):
        if target not in pages:
            findings.append(dict(code="missing_entry", page=target))
        elif target not in reached:
            findings.append(dict(code="unreachable_entry", page=target))
    route_pages = {entry, *required, "wiki/notes/v3/index.md", "wiki/notes/v3-migration.md", "wiki/notes/v3/recipes.md"}
    for relative, (fields, _) in pages.items():
        if relative.startswith(("wiki/notes/", "wiki/projects/")) and relative not in route_pages and relative not in reached:
            findings.append(dict(code="unreachable_page", page=relative))
        topics = fields.get("os_topics", [])
        if (relative.startswith("wiki/notes/") and not relative.startswith("wiki/notes/topics/")
                and fields.get("os_topic_state") == "classified" and isinstance(topics, list)):
            for identifier in topics:
                if topic_id(identifier):
                    category = f"wiki/notes/topics/{identifier}.md"
                    if relative not in edges.get(category, set()):
                        findings.append(dict(code="topic_member_unlisted", page=relative, source=category))
    unique = {json.dumps(finding, sort_keys=True): finding for finding in findings}
    findings = [unique[key] for key in sorted(unique)]
    return dict(read_only=True, entry=entry, pages_scanned=len(pages), pages_reachable=len(reached),
                findings=findings, counts=dict(sorted((code, sum(item["code"] == code for item in findings))
                                                    for code in {item["code"] for item in findings})),
                limitations=["通常の相対Markdownリンクのみ。HTML・動的検索・リンク先の見出しは判定しない",
                             "レシピ全件はtools/recipes.mdの一覧から発見する。本文の有用性や判断の正しさは判定しない",
                             "リンク欄が古くても所属の正本と本文検索を確認する。結果だけで自動補修しない"])


def audit_migration_completion(root):
    """Opt-in handoff check, never a persistent requirement to keep projects active."""
    root = Path(root).resolve()
    findings, advisories = [], []
    copied = 0
    project_index = root / 'wiki/projects/index.md'
    listed_projects = set()
    if project_index in safe_files(root, root / 'wiki/projects', 'index.md'):
        try:
            _, index_body = front_matter(project_index.read_text(encoding='utf-8'))
            for target in navigation_links(index_body):
                if local_reference(target):
                    listed_projects.add(posixpath.normpath(posixpath.join('wiki/projects', unquote(target.split('#', 1)[0]))))
        except (OSError, UnicodeError):
            pass  # The navigation audit reports unreadable/missing entry pages.

    def date(value):
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return None
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return None

    def copied_directory(value):
        # This is a filesystem path, not a URL. Do not normalize away traversal or follow links.
        if not isinstance(value, str) or not local_reference(value) or '#' in value or '%' in value:
            return False
        parts = value.rstrip('/').split('/')
        if len(parts) < 2 or parts[0] != 'projects' or any(part in ('', '.', '..') for part in parts):
            return False
        current = root
        try:
            for part in parts:
                current = current / part
                if not stat.S_ISDIR(current.lstat().st_mode):
                    return False
        except OSError:
            return False
        return True

    for path in safe_files(root, root / 'wiki/projects', '*.md'):
        relative = path.relative_to(root).as_posix()
        try:
            fields, body = front_matter(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError):
            findings.append(dict(code='unreadable_page', page=relative))
            continue
        if fields.get('os_output_state') != 'copied':
            continue
        copied += 1
        if relative not in listed_projects:
            findings.append(dict(code='copied_output_unlisted', page=relative, source='wiki/projects/index.md'))
        if not fields.get('path'):
            findings.append(dict(code='copied_output_missing_path', page=relative))
        elif not copied_directory(fields['path']):
            findings.append(dict(code='copied_output_directory_unavailable', page=relative))
        # Inspect only the generated current section and next field, never preserved v3 documents.
        generated = re.split(r'^## (?:README|v3 の紹介カード).*$', body, maxsplit=1, flags=re.M)[0]
        current = re.search(r'^#{2,3} いまの状況[^\S\n]*\n(.*?)(?=^#{1,3} |\Z)', generated, re.M | re.S)
        stale_current = current and any(phrase in current[1] for phrase in
                                       ('ワークスペースにはまだ写していない', 'まだ再開していない'))
        stale_next = str(fields.get('next', '')).startswith('続けるなら、写してよいかを本人に聞いてから、v3 の output/')
        if stale_current or stale_next:
            findings.append(dict(code='copied_output_stale_text', page=relative))
        copied_at, updated = date(fields.get('os_output_copied_at')), date(fields.get('updated'))
        if not copied_at or not updated or copied_at != updated:
            advisories.append(dict(code='copied_output_date_mismatch', page=relative))
        # A dated later transition to done/paused is legitimate. Same-day transitions cannot be
        # distinguished with date-only metadata: this mode is explicitly for the initial handoff.
        later_transition = copied_at and updated and updated > copied_at and fields.get('status') in ('done', 'paused')
        if fields.get('status') != 'active' and not later_transition:
            findings.append(dict(code='copied_output_not_active_at_completion', page=relative))

    index = build_index(root)
    linked = set()
    for page in index['pages']:
        if page['related']:
            linked.add(page['key'])
            linked.update(page['related'])
    for page in index['pages']:
        if not page['navigation'] and page['collection'] in ('projects', 'v3', 'recipes') and page['key'] not in linked:
            advisories.append(dict(code='isolated_reference_page', page=page['path']))
    for reference in index['diagnostics']['references']:
        if reference['status'] in ('missing', 'ambiguous', 'not_migrated'):
            source = next((page['path'] for page in index['pages'] if page['key'] == reference['source']),
                          reference['source'] + '.md')
            broken_link = reference['relation'] == 'body' and reference['status'] in ('missing', 'not_migrated')
            (findings if broken_link else advisories).append(
                dict(code='missing_reference_page' if broken_link else 'unresolved_reference', page=source,
                     relation=reference['relation'], status=reference['status'], target=reference['reference']))
    return dict(read_only=True, copied_projects_scanned=copied, findings=findings, advisories=advisories,
                limitations=['コピー済み印のある案件だけを検査。成果物の内容一致・動作・機密検査はしない',
                             'active は移行完了時だけの条件。後日の通常点検ではこのオプションを使わない。日付だけでは同日の状態変更を区別できない',
                             'updated がコピー日より後の done/paused は許容。日付差・関係線の孤立・未解決メタ情報は参考情報であり失敗にしない。本文リンクの参照先欠落は指摘する'])


def read_page(root, p, rel, col):
    text = p.read_text(encoding="utf-8", errors="replace")
    fm, body = front_matter(text)
    if col == "recipes":
        rid = str(fm.get("id") or (p.parent.name if p.name == "RECIPE.md" else p.stem))
        rj = p.parent / "recipe.json"
        if p.name == "RECIPE.md" and rj.is_file() and not rj.is_symlink() and os.stat(rj).st_nlink == 1 \
                and os.path.realpath(rj).startswith(os.path.realpath(root / "recipes") + os.sep):  # 外のファイル・ハードリンクは読まない
            try:
                spec = json.loads(rj.read_text(encoding="utf-8"))
                if not isinstance(spec, dict):
                    spec = {}
                rid = str(spec.get("id") or rid)
                fm.setdefault("title", spec.get("name") or rid)
                fm.setdefault("summary", spec.get("summary") or "")
                fm.setdefault("version", spec.get("version") or "")
            except (ValueError, OSError):
                pass
        key = rel[: -len("/RECIPE.md")] if p.name == "RECIPE.md" else rel[:-3]
    else:
        rid = str(fm.get("id") or p.stem)
        key = rel[:-3]
    h1 = re.search(r"^#\s+(.+)$", body, re.M)
    title = str(fm.get("title") or (h1.group(1).strip() if h1 else p.stem))
    summary = str(fm.get("summary") or fm.get("next") or first_line(body))
    shown = {k: v for k, v in fm.items() if k not in ("title", "summary")}
    if "os_topic_id" in fm and "title" in fm:
        shown["title"] = fm["title"]
    return {"key": key, "collection": col, "id": rid, "path": rel, "title": title, "summary": summary,
            "status": str(fm.get("status") or ""), "updated": str(fm.get("updated") or ""), "created": str(fm.get("created") or ""),
            "tags": fm.get("tags") if isinstance(fm.get("tags"), list) else [], "fm": shown,
            "body": body.strip(), "edit": edit_target(col, rel), "_body_for_links": body}


# ---------------------------------------------------------------- サーバー
def root_id(root):
    return hashlib.sha1(os.path.normcase(os.path.realpath(root)).encode("utf-8")).hexdigest()[:12]


def make_handler(root, port):
    rid = root_id(root)
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def refuse(self):
            h = self.headers.get_all("Host") or []
            o = self.headers.get_all("Origin") or []
            if len(h) != 1 or h[0].strip().lower() not in hosts or len(o) > 1 or (o and o[0].strip().lower() not in origins):
                self.send_error(403)
                return True
            return False

        def send(self, code, body, ctype, policy=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            if policy:
                self.send_header("Content-Security-Policy", policy)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Wiki-Root", rid)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if self.refuse():
                return
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            if path in ("/", "/view"):
                self.send_response(302)
                self.send_header("Location", "/view/")
                self.send_header("X-Wiki-Root", rid)
                self.end_headers()
                return
            if path == "/view/index.json":
                try:
                    body, code = json.dumps(view_index(root), ensure_ascii=False).encode("utf-8"), 200
                except Exception as e:  # 壊れたページがあっても、理由だけ返す（フォルダの場所は出さない）
                    print(f"wiki_view: index.json: {e!r}", file=sys.stderr)
                    body, code = json.dumps({"error": type(e).__name__, "pages": [], "collections": []}).encode("utf-8"), 500
                return self.send(code, body, "application/json; charset=utf-8")
            if path in ("/view/", "/admin/"):
                path += "index.html"
            m = re.match(r"^/(view|admin)/([A-Za-z0-9_.\-]+)$", path)
            if not m or m.group(2).startswith("."):
                return self.send_error(404)
            base = UI if m.group(1) == "view" else UI / "admin"
            f = base / m.group(2)
            ext = f.suffix.lower()
            if ext not in STATIC or f.is_symlink() or not f.is_file():
                return self.send_error(404)
            data = f.read_bytes()
            self.send(200, data, STATIC[ext], csp(data) if ext == ".html" else None)

    return Handler


def serve(root, port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(root, port))
    print(f"Wiki の画面: http://127.0.0.1:{port}/view/（止める: Ctrl+C か python3 tools/wiki_view.py stop）", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def ours(root, port):
    """そのポートで、このワークスペースの Wiki のサーバーが動いているか。"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/view/index.html", timeout=1.5) as r:
            return r.headers.get("X-Wiki-Root") == root_id(root)
    except Exception:
        return False


def free(port):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def pidfile(root):
    return Path(tempfile.gettempdir()) / f"kb-wiki-view-{root_id(root)}.json"


def start(root):
    """裏で動いていればそのポート、なければ空いているポートで裏に起動する。→ port"""
    pf = pidfile(root)
    if pf.is_file():
        try:
            port = json.loads(pf.read_text())["port"]
            if ours(root, port):
                return port
        except (ValueError, KeyError, OSError):
            pass
    port = next((p for p in range(PORT, PORT + 30) if ours(root, p) or free(p)), None)
    if port is None:
        raise SystemExit("空いているポートが見つかりません")
    if ours(root, port):
        return port
    log = open(Path(tempfile.gettempdir()) / f"kb-wiki-view-{root_id(root)}.log", "a")
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "serve", "--port", str(port), "--root", str(root)],
                            stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(50):
        if ours(root, port):
            pf.write_text(json.dumps({"port": port, "pid": proc.pid}))
            return port
        time.sleep(0.1)
    raise SystemExit("サーバーを起動できませんでした（ログ: " + log.name + "）")


def open_browser(url, chromium):
    if sys.platform == "darwin":
        apps = ["Google Chrome", "Microsoft Edge", "Brave Browser", "Chromium"] if chromium else [None]
        for app in apps:
            cmd = ["open", url] if app is None else ["open", "-a", app, url]
            if subprocess.run(cmd, capture_output=True).returncode == 0:
                return app or "既定のブラウザ"
        return None
    import webbrowser
    return "既定のブラウザ" if webbrowser.open(url) else None


def main():
    ap = argparse.ArgumentParser(description="Wiki をグラフと画面で見る・Sveltia で直す")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open")
    o.add_argument("page", nargs="?", default="graph", choices=["view", "graph", "3d", "edit"])
    o.add_argument("--no-browser", action="store_true")
    sub.add_parser("stop")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=PORT)
    s.add_argument("--root", default=".")
    j = sub.add_parser("json")
    j.add_argument("--root", default=".")
    d = sub.add_parser("diagnose")
    d.add_argument("--root", default=".")
    audit = sub.add_parser("audit")
    audit.add_argument("--root", default=".")
    audit.add_argument("--migration-completion", action="store_true",
                       help="移行完了時だけコピー済み案件を点検（保存しない。後日の状態変更を強制しない）")
    a = ap.parse_args()
    root = Path(getattr(a, "root", ".")).resolve()
    if not (root / "wiki").is_dir():
        raise SystemExit("ワークスペースのいちばん上（wiki/ があるフォルダ）で実行してください")
    if a.cmd == "audit":
        data = audit_navigation(root)
        if a.migration_completion:
            data['migration_completion'] = audit_migration_completion(root)
        print(json.dumps(data, ensure_ascii=False, indent=1))
        raise SystemExit(1 if data["findings"] or data.get('migration_completion', {}).get('findings') else 0)
    elif a.cmd in ("json", "diagnose"):
        data = build_index(root) if a.cmd == "diagnose" else view_index(root)
        print(json.dumps(data["diagnostics"] if a.cmd == "diagnose" else data, ensure_ascii=False, indent=1))
    elif a.cmd == "serve":
        serve(root, a.port)
    elif a.cmd == "stop":
        pf = pidfile(root)
        if not pf.is_file():
            print("裏で動いているサーバーはありません")
            return
        info = json.loads(pf.read_text())
        if ours(root, info["port"]):
            os.kill(info["pid"], 15)
        pf.unlink(missing_ok=True)
        print("止めました")
    else:
        port = start(root)
        url = f"http://127.0.0.1:{port}/" + {"view": "view/", "graph": "view/#/graph", "3d": "view/graph.html", "edit": "admin/"}[a.page]
        print(f"開く場所: {url}")
        print(f"Wiki本体: http://127.0.0.1:{port}/view/")
        print(f"Sveltia CMS（管理画面）: http://127.0.0.1:{port}/admin/")
        print(f"グラフビュー: http://127.0.0.1:{port}/view/#/graph")
        if a.page == "edit":
            print("Sveltia CMS: 「ローカルリポジトリで作業」（英語の画面では Work with Local Repository）を押し、ワークスペースのフォルダ（wiki/ と .git があるフォルダ）を選ぶ。"
                  "保存するとワークスペースのファイルが直接変わる（commit はしない。Sveltia の設定の「ローカルの変更を commit する」は OFF のままにする）。Chrome・Edge などで開く（Safari では使えない）")
        if not a.no_browser and not os.environ.get("WIKI_VIEW_NO_BROWSER"):  # 試験ではブラウザを開かない
            used = open_browser(url, chromium=a.page == "edit")
            print(f"ブラウザ: {used}" if used else "ブラウザを開けませんでした。上の場所を開いてください")


if __name__ == "__main__":
    main()

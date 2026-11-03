#!/usr/bin/env python3
"""Read-only plan, approved copy and resumable Wiki handoff for v3 output."""
import argparse
import base64
import datetime
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import posixpath
import re
import stat
import sys
import unicodedata
from contextlib import contextmanager
from urllib.parse import quote
from types import SimpleNamespace

sys.dont_write_bytecode = True
STATE = "tools/.state/output-migration"
SKIP_DIRS = {".git", "node_modules", ".wrangler", ".venv", "venv", "__pycache__",
             ".next", ".turbo", ".cache", ".svelte-kit", ".aws", ".ssh", ".docker", ".terraform"}
SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini", "Icon\r"}
SECRET = re.compile(r"^(?:\.env(?:\..*)?|\.envrc|\.dev\.vars(?:\..*)?|.*\.(?:pem|key|p12|pfx)|"
                    r"id_(?:rsa|ed25519|ecdsa)(?:\.pub)?|.*credentials.*\.json|settings\.local\.json|"
                    r"service[-_]?account.*\.json|\.netrc|\.npmrc|\.pypirc|credentials|\.git-credentials|"
                    r"token\.(?:json|pickle)|client_secret.*\.json|.*\.(?:keystore|jks|ppk|tfstate)(?:\.backup)?|\.mcp\.json)$", re.I)
TEMPLATE = re.compile(r"^\.(?:env|dev\.vars)\.(?:example|sample|template)$", re.I)


class Stop(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def module(name):
    spec = importlib.util.spec_from_file_location("output_" + name, Path(__file__).with_name(name + ".py"))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def relative(value):
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        raise Stop("相対パスの形式が不正です")
    for part in value.split("/"):
        if (part in ("", ".", "..") or part[-1:] in (" ", ".") or
                re.search(r'[<>:"|?*\x00-\x1f\x7f]', part) or
                re.fullmatch(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part, re.I)):
            raise Stop("Windowsでも安全に扱える相対パスが必要です")
    return value


def linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def checked(root, value):
    current = root
    if linked(root.lstat()):
        raise Stop("ルートがリンクです")
    for part in relative(value).split("/"):
        current = current / part
        if os.path.lexists(current):
            info = current.lstat()
            if linked(info) or (not stat.S_ISDIR(info.st_mode) and
                                (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
                raise Stop("リンク・hardlink・特殊ファイルを通るパスは使えません: " + value)
    return current


def canonical(path):
    path = path.absolute()
    if linked(path.lstat()) or not path.is_dir():
        raise Stop("移行元・ワークスペースにはリンクでないフォルダを指定してください")
    return path.resolve()


def read(root, value, limit=16 * 1024 * 1024):
    path = checked(root, value)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or linked(before):
            raise Stop("通常の単独ファイルではありません: " + value)
        if before.st_size > limit:
            raise Stop("読取り上限を超えています: " + value)
        data = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise Stop("読取り中に変更されました: " + value)
    return data


def fingerprint(root, value, paired=False):
    path = root / relative(value) if paired else checked(root, value)
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)), "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != (2 if paired else 1) or linked(before):
            raise Stop("通常ファイルの実体を確認できません: " + value)
        checksum = hashlib.sha256()
        while chunk := handle.read(1024 * 1024):
            checksum.update(chunk)
        after = os.fstat(handle.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise Stop("照合中にファイルが変わりました: " + value)
    return {"sha256": checksum.hexdigest(), "size": after.st_size,
            "mode": 0o755 if after.st_mode & 0o111 else 0o644}


def split_page(text):
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)(.*)\Z", text, re.S)
    if not match:
        raise Stop("案件ページに通常のfront matterが必要です")
    lines = match[1].splitlines()
    fields = {}
    for line in lines:
        field = re.match(r"^([\w-]+):\s*(.*?)\s*$", line)
        if field:
            if field[1] in fields:
                raise Stop("front matterの項目が重複しています")
            value = field[2]
            if value.startswith('"'):
                try:
                    value = json.loads(value)
                except ValueError as error:
                    raise Stop("front matterの引用形式を確認してください") from error
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("''", "'")
            fields[field[1]] = value
    return fields, lines, match[2]


def inventory(source, project, includes):
    files, skipped, directories = [], [], []
    start = checked(source, project)
    if not start.is_dir():
        raise Stop("元の案件フォルダがありません: " + project)
    def visit(directory):
        names = set()
        for path in sorted(directory.iterdir()):
            key = unicodedata.normalize("NFC", path.name).casefold()
            if key in names:
                raise Stop("大文字小文字・Unicode表記が衝突しています")
            names.add(key)
            name = path.relative_to(source).as_posix()
            if path.name in SKIP_FILES:
                skipped.append({"path": name, "reason": "system_metadata"})
                continue
            try:
                relative(name)
            except Stop:
                skipped.append({"path": name, "reason": "windows_unsafe_name"})
                continue
            info = path.lstat()
            reason = None
            if path.name.casefold() == ".git":
                reason = "dependency_or_git"
            elif linked(info):
                reason = "link"
            elif stat.S_ISDIR(info.st_mode):
                if path.name.casefold() in SKIP_DIRS:
                    reason = "dependency_or_git"
                else:
                    directories.append(name)
                    visit(path)
                    continue
            elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                reason = "special_or_hardlink"
            elif path.name in SKIP_FILES:
                reason = "system_metadata"
            elif SECRET.match(path.name) and name not in includes:
                reason = "secret_or_unreviewed_template"
            if reason:
                skipped.append({"path": name, "reason": reason})
                continue
            if name in includes:
                if not TEMPLATE.fullmatch(path.name):
                    raise Stop("秘密ファイルの一括許可はできません。ひな形だけを個別指定してください")
                try:
                    text = read(source, name).decode("utf-8")
                except UnicodeError as error:
                    raise Stop("ひな形はUTF-8テキストだけを確認できます") from error
                if "\x00" in text or module("migrate_v3").secret_lines(text):
                    raise Stop("ひな形に秘密らしい値があります。内容は表示せず停止しました")
            files.append({"path": name, **fingerprint(source, name)})
    visit(start)
    return {"files": files, "directories": directories, "excluded": skipped,
            "git_present": os.path.lexists(start / ".git")}


def replace_region(text, namespace, body):
    start, end = f"<!-- {namespace}:begin -->", f"<!-- {namespace}:end -->"
    replacement = start + "\n" + body.strip() + "\n" + end
    if start in text or end in text:
        if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
            raise Stop("生成欄の境界が不正です: " + namespace)
        return text[:text.index(start)] + replacement + text[text.index(end) + len(end):]
    return text.rstrip() + "\n\n" + replacement + "\n"


def update_page(original, item, today):
    fields, lines, body = split_page(original)
    updates = {"status": "active", "path": item["destination"], "updated": today,
               "next": "動作確認の範囲を本人と決めてから、続きに取り組む（動作は未確認）",
               "os_output_state": "copied", "os_output_copied_at": today}
    for key, value in updates.items():
        pattern = re.compile(r"^" + re.escape(key) + r":")
        replacement = key + ": " + json.dumps(value, ensure_ascii=False)
        matches = [number for number, line in enumerate(lines) if pattern.match(line)]
        if matches:
            lines[matches[0]] = replacement
        else:
            lines.append(replacement)
    source = item["source"]
    old = f"- 成果物（コード）は v3 の `{source}/` にあり、ワークスペースにはまだ写していない。写す先は `{item['destination']}/`（v3 の場所は [移行の記録](../notes/v3-migration.md)）"
    body = body.replace(old, f"- 成果物を `{item['destination']}/` にコピー・照合済み。元のv3は保持。動作は未確認。", 1)
    body = re.sub(r"^- \d{4}-\d{2}-\d{2} に kote2 Builder v3 から移した。まだ再開していない$",
                  f"- {today} に成果物をコピー・照合し、案件を active にした。動作は未確認。", body, count=1, flags=re.M)
    summary = (f"- {today}: 成果物を `{item['destination']}/` へコピーし、SHA-256で照合。状態は active。\n"
               "- 元のv3は変更していない。動作確認・外部接続・独自Gitの保存は未実施。\n"
               "- [一括コピーの記録](../notes/output-migration-" + item["batch"] + ".md)")
    current = re.search(r"^#{2,3} いまの状況[^\S\n]*\n(.*?)(?=^#{1,3} |\Z)", body, re.M | re.S)
    if current:
        section = replace_region(body[current.start():current.end()], "os-output-copy", summary)
        body = body[:current.start()] + section + "\n" + body[current.end():]
    else:
        body = "### いまの状況\n" + replace_region("", "os-output-copy", summary) + "\n" + body
    current = re.search(r"^#{2,3} いまの状況[^\S\n]*\n(.*?)(?=^#{1,3} |\Z)", body, re.M | re.S)
    if current and any(phrase in current[1] for phrase in
                       ("ワークスペースにはまだ写していない", "まだ再開していない")):
        raise Stop("いまの状況の未コピー記述を安全に更新できません。案件ページを確認してからscanし直してください: " + item["page"])
    if item.get("recipe_links"):
        links = "\n".join("- [出典を確認できたレシピ](" +
                          quote(posixpath.relpath(target, "wiki/projects"), safe="/.-_~") + ")"
                          for target in item["recipe_links"])
        if "<!-- os-output-recipes:begin -->" in body:
            body = replace_region(body, "os-output-recipes", links)
        else:
            preserved = re.search(r"^## (?:README|v3 の紹介カード).*$", body, re.M)
            offset = preserved.start() if preserved else len(body)
            body = body[:offset].rstrip() + "\n\n" + replace_region("", "os-output-recipes", links) + "\n" + body[offset:]
    decision = f"- {today}: 承認済みの一括移行計画に基づき、元を残して成果物をコピーし active に変更。"
    heading = re.search(r"^#{2,3} 決定ログ\s*$", body, re.M)
    if heading:
        body = body[:heading.end()] + "\n" + decision + body[heading.end():]
    else:
        body += "\n### 決定ログ\n" + decision + "\n"
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def make_plan(source, workspace, projects, all_projects=False, includes=()):
    if source == workspace or source in workspace.parents or workspace in source.parents:
        raise Stop("移行元とワークスペースは互いに外側の独立したフォルダが必要です")
    checked(source, "output")
    checked(workspace, "wiki/projects")
    includes = sorted({relative(value) for value in includes})
    if any(len(value.split("/")) != 3 or not value.startswith("output/") or
           value.split("/")[-1] != ".env.example" for value in includes):
        raise Stop("ひな形は output/<案件名>/.env.example だけを個別指定してください")
    candidates = {}
    for path in sorted((workspace / "wiki/projects").glob("*.md")):
        data = read(workspace, path.relative_to(workspace).as_posix())
        fields, _, _ = split_page(data.decode("utf-8")) if data.startswith(b"---") else ({}, [], "")
        if fields.get("v3_path"):
            candidates[path.stem] = (fields, data)
    already_copied = sorted(name for name, (fields, _) in candidates.items() if fields.get("os_output_state") == "copied")
    selected = sorted(set(candidates) - set(already_copied)) if all_projects else sorted(set(projects))
    if (not selected and not (all_projects and already_copied)) or set(selected) - candidates.keys():
        raise Stop("移行済みの案件ページを --project で選ぶか --all を指定してください")
    items, wiki = [], {}
    recipe_files, dependencies = [], {}
    recipe_root = checked(workspace, "recipes")
    if recipe_root.exists():
        for directory, folders, filenames in os.walk(recipe_root, followlinks=False):
            folders[:] = sorted(name for name in folders if name.casefold() not in SKIP_DIRS and
                                not linked((Path(directory) / name).lstat()))
            for filename in sorted(filenames):
                if filename.endswith(".md") or filename == "recipe.json":
                    path = (Path(directory) / filename).relative_to(workspace).as_posix()
                    data = read(workspace, path)
                    dependencies[path] = digest(data)
                    recipe_files.append((path, path, data))
    migration = module("migrate_v3")
    catalog = migration.project_recipe_catalog(SimpleNamespace(recipe_files=recipe_files))
    identities = set()
    for name in selected:
        relative(name)
        if "/" in name:
            raise Stop("案件ページのファイル名だけを指定してください")
        fields, data = candidates[name]
        original = relative(str(fields["v3_path"]).rstrip("/"))
        if len(original.split("/")) != 2 or not original.startswith("output/"):
            raise Stop("v3_pathは output/<案件名>/ の形式が必要です")
        identity = unicodedata.normalize("NFC", name).casefold()
        if identity in identities:
            raise Stop("コピー先の案件名が衝突しています")
        identities.add(identity)
        destination = "projects/" + name
        if os.path.lexists(checked(workspace, destination)):
            raise Stop("コピー先がすでにあります。上書きせず停止します: " + destination)
        detail = inventory(source, original, includes)
        item = dict(name=name, title=str(fields.get("title", name)), source=original,
                    destination=destination, page="wiki/projects/" + name + ".md",
                    recipe_links=sorted({entry["destination"] for entry in catalog.values()
                                         if original + "/" in entry["sources"]}), **detail)
        items.append(item)
        wiki[item["page"]] = {"before": digest(data), "original": data.decode("utf-8")}
    seen_includes = {entry["path"] for item in items for entry in item["files"]} & set(includes)
    if seen_includes != set(includes):
        raise Stop("ひな形の個別指定が選択案件の通常ファイルと一致しません")
    for path in ("wiki/index.md", "wiki/projects/index.md", "wiki/notes/index.md"):
        checked(workspace, path)
        data = read(workspace, path) if (workspace / path).exists() else None
        wiki[path] = {"before": digest(data) if data is not None else None,
                      "original": data.decode("utf-8") if data is not None else "# 案件の一覧\n"}
    plan = dict(format=1, source=str(source), workspace=str(workspace), includes=includes,
                date=datetime.date.today().isoformat(), projects=items, wiki=wiki,
                dependencies=dependencies, already_copied=already_copied if all_projects else [],
                existing_findings=module("wiki_view").audit_migration_completion(workspace)["findings"],
                tool_sha256=digest(Path(__file__).read_bytes()))
    if not items:
        plan["wiki"] = {}
        plan["id"] = digest(encoded(plan))
        return plan
    batch = digest(encoded(plan))
    for item in items:
        item["batch"] = batch
        wiki[item["page"]]["after"] = update_page(wiki[item["page"]]["original"], item, plan["date"])
    project_index = wiki["wiki/projects/index.md"]["original"]
    active_links = []
    for item in items:
        target = re.escape(quote(item["name"] + ".md"))
        pattern = re.compile(r"^- \[[^\n]*\]\(" + target + r"\)[^\n]*$", re.M)
        existing = pattern.findall(project_index)
        label = item["title"].replace("[", "\\[").replace("]", "\\]")
        if existing:
            for line in existing:
                if re.search(r"（(?:active|paused|done)）", line):
                    line = re.sub(r"（(?:active|paused|done)）", "（active）", line)
                else:
                    line = line.replace("](", "（active）](", 1)
                active_links.append(line)
        else:
            active_links.append(f"- [{label}（active）]({quote(item['name'] + '.md')})")
        if existing:
            project_index = pattern.sub("", project_index)
    if re.search(r"^## (?:active|進行中（active）)[^\S\n]*$", project_index, re.M):
        project_index = re.sub(r"(^## (?:active|進行中（active）)[^\S\n]*$)",
                               lambda match: match[0] + "\n" + "\n".join(active_links), project_index, count=1, flags=re.M)
    else:
        project_index += "\n## active\n" + "\n".join(active_links) + "\n"
    wiki["wiki/projects/index.md"]["after"] = project_index
    overview_lines = []
    overview = wiki["wiki/index.md"]["original"]
    for item in items:
        pattern = re.compile(r"^- \[[^\n]*\]\(projects/" + re.escape(quote(item["name"] + ".md")) + r"\)[^\n]*$", re.M)
        existing = pattern.findall(overview)
        overview = pattern.sub("", overview)
        overview_lines += ([re.sub(r"（(?:active|paused|done)）", "（active）", line) for line in existing] if existing else
                           [f"- [{item['name']}（active）](projects/{quote(item['name'] + '.md')})"])
    wiki["wiki/index.md"]["after"] = replace_region(overview, "os-output-" + batch, "\n".join(overview_lines))
    record_path = f"wiki/notes/output-migration-{batch}.md"
    if os.path.lexists(checked(workspace, record_path)):
        raise Stop("同じコピー記録が既にあります")
    lines = ["---", "title: output一括コピーの記録", "updated: " + plan["date"], "---", "",
             "元のv3を残し、承認された対象だけをコピー・SHA-256照合した。動作・外部接続・Git保存は未確認。", ""]
    for item in items:
        lines += [f"- [{item['name']}](../projects/{quote(item['name'] + '.md')}) → `{item['destination']}/`（active）",
                  f"  - 照合対象 {len(item['files'])} ファイル、除外 {len(item['excluded'])} 件。Git履歴はコピーしていない。"]
    wiki[record_path] = {"before": None, "after": "\n".join(lines) + "\n"}
    wiki["wiki/notes/index.md"]["after"] = replace_region(
        wiki["wiki/notes/index.md"]["original"], "os-output-" + batch,
        f"- [output一括コピーの記録（{plan['date']}）](output-migration-{batch}.md)")
    for change in wiki.values():
        change.pop("original", None)
    plan["id"] = digest(encoded(plan))
    if len(encoded(plan)) > 128 * 1024 * 1024:
        raise Stop("計画が128MiBを超えています。案件を分割してscanしてください")
    return plan


def public_plan(plan):
    return {"plan": plan["id"], "date": plan["date"], "read_only": True,
            "already_copied": plan["already_copied"], "existing_findings": plan["existing_findings"],
            "projects": [{key: value for key, value in item.items() if key not in ("files", "directories", "batch")} |
                         {"files": len(item["files"]), "bytes": sum(entry["size"] for entry in item["files"]),
                          "large_files": [entry["path"] for entry in item["files"] if entry["size"] > 5 * 1024 * 1024]}
                         for item in plan["projects"]],
            "wiki_updates": sorted(plan["wiki"]),
            "wiki_diff": {path: "".join(difflib.unified_diff(
                (read(Path(plan["workspace"]), path).decode("utf-8") if change["before"] is not None else "").splitlines(True),
                change["after"].splitlines(True), fromfile=path, tofile=path)) for path, change in plan["wiki"].items()},
            "secret_check": "filename-based exclusions; contents not scanned except explicitly approved .env.example; not a guarantee of no secrets",
            "git_policy": "files-only; Git保存と動作確認は別の了承が必要"}


def ensure_directory(root, value):
    path = checked(root, value)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    checked(root, value)
    return path


def write_new(root, value, data, mode=0o644):
    ensure_directory(root, Path(value).parent.as_posix())
    path = checked(root, value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags, mode), "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def replace_file(root, value, data):
    ensure_directory(root, Path(value).parent.as_posix())
    path = checked(root, value)
    temporary = STATE + "/staging/" + digest(value.encode()) + "-" + digest(data) + ".tmp"
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else (0o600 if value.startswith(STATE + "/") else 0o644)
    if os.path.lexists(checked(root, temporary)):
        existing = read(root, temporary, max(16 * 1024 * 1024, len(data)))
        if not data.startswith(existing):
            raise Stop("内部の一時ファイルに追加編集があります。保持して停止します")
        checked(root, temporary).unlink()
    write_new(root, temporary, data, mode)
    os.replace(checked(root, temporary), path)


def save_journal(workspace, journal):
    stored = {key: value for key, value in journal.items() if key not in ("journal_hash", "plan")}
    stored["plan_id"] = journal["plan"]["id"]
    stored["journal_hash"] = digest(encoded(stored))
    replace_file(workspace, STATE + "/transaction.json", encoded(stored) + b"\n")


def load_journal(workspace):
    journal = json.loads(read(workspace, STATE + "/transaction.json"))
    if (not isinstance(journal, dict) or journal.get("phase") not in ("copying", "wiki", "complete") or
            not isinstance(journal.get("owned"), list) or
            not re.fullmatch(r"[a-f0-9]{64}", str(journal.get("plan_id", ""))) or
            journal.get("journal_hash") != digest(encoded({key: value for key, value in journal.items() if key != "journal_hash"}))):
        raise Stop("中断記録の形式または整合性を確認できません")
    journal["plan"] = json.loads(read(workspace, STATE + "/plans/" + journal["plan_id"] + ".json", 128 * 1024 * 1024))
    if journal["plan"].get("id") != journal["plan_id"]:
        raise Stop("中断計画の識別子が一致しません")
    destinations = {item["destination"] for item in journal["plan"]["projects"]}
    if set(journal["owned"]) - destinations:
        raise Stop("中断記録の所有先が計画外です")
    plan = journal["plan"]
    if digest(encoded({key: value for key, value in plan.items() if key != "id"})) != plan["id"]:
        raise Stop("中断計画のhashが一致しません")
    return journal


def copy_file(plan, item, entry, workspace, journal):
    source = Path(plan["source"])
    suffix = Path(entry["path"]).relative_to(item["source"]).as_posix()
    destination = item["destination"] + "/" + suffix
    temporary = STATE + "/staging/" + plan["id"] + "-" + digest(destination.encode()) + ".part"
    pending = {"destination": destination, "temporary": temporary, "source": entry["path"]}
    if journal.get("pending_file") not in (None, pending):
        raise Stop("別のファイルのコピーが中断しています")
    journal["pending_file"] = pending
    save_journal(workspace, journal)
    ensure_directory(workspace, Path(destination).parent.as_posix())
    ensure_directory(workspace, Path(temporary).parent.as_posix())
    target, staging = workspace / destination, workspace / temporary
    if os.path.lexists(target) and os.path.lexists(staging) and not linked(target.lstat()) and not linked(staging.lstat()) and os.path.samestat(target.lstat(), staging.lstat()):
        if fingerprint(workspace, destination, paired=True)["sha256"] != entry["sha256"]:
            raise Stop("一時コピーの照合が一致しません")
        staging.unlink()
    if os.path.lexists(checked(workspace, destination)):
        if fingerprint(workspace, destination)["sha256"] != entry["sha256"]:
            raise Stop("コピー先に本人編集があります。上書きしません")
    else:
        offset = 0
        if os.path.lexists(checked(workspace, temporary)):
            if staging.stat().st_size > entry["size"]:
                raise Stop("一時コピーのサイズが計画を超えています")
            with open(checked(source, entry["path"]), "rb") as original, open(checked(workspace, temporary), "rb") as partial:
                while chunk := partial.read(1024 * 1024):
                    if chunk != original.read(len(chunk)):
                        raise Stop("一時コピーに追加編集があります。保持して停止します")
                    offset += len(chunk)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        with open(checked(source, entry["path"]), "rb") as original, os.fdopen(os.open(checked(workspace, temporary), flags, entry["mode"]), "ab") as output:
            original.seek(offset)
            while chunk := original.read(1024 * 1024):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if fingerprint(workspace, temporary)["sha256"] != entry["sha256"]:
            raise Stop("一時コピーの照合が一致しません")
        os.link(checked(workspace, temporary), checked(workspace, destination))
        staging.unlink()
    journal["pending_file"] = None
    save_journal(workspace, journal)


def validate_plan(plan, source, workspace):
    if plan.get("source") != str(source) or plan.get("workspace") != str(workspace):
        raise Stop("移行元またはワークスペースが承認時と違います")
    identity = plan.get("id")
    if digest(encoded({key: value for key, value in plan.items() if key != "id"})) != identity:
        raise Stop("保存された計画が変更されています")
    if digest(Path(__file__).read_bytes()) != plan["tool_sha256"]:
        raise Stop("コピーの道具が計画から変わりました。保存記録を確認してください")
    for path, checksum in plan["dependencies"].items():
        if digest(read(workspace, path)) != checksum:
            raise Stop("関連レシピが計画から変わりました。再承認してください")
    for item in plan["projects"]:
        if inventory(source, item["source"], plan["includes"]) != {key: item[key] for key in ("files", "directories", "excluded", "git_present")}:
            raise Stop("元データが計画から変わりました。上書きせず停止します")
    for path, change in plan["wiki"].items():
        actual = digest(read(workspace, path)) if os.path.lexists(checked(workspace, path)) else None
        if actual not in (change["before"], digest(change["after"].encode())):
            raise Stop("Wikiに追加編集があります。上書きしません: " + path)


def verify_copy(plan, workspace):
    for item in plan["projects"]:
        destination = item["destination"]
        includes = [destination + "/" + Path(name).relative_to(item["source"]).as_posix()
                    for name in plan["includes"] if name.startswith(item["source"] + "/")]
        actual = inventory(workspace, destination, includes)
        wanted = {Path(entry["path"]).relative_to(item["source"]).as_posix(): (entry["sha256"], entry["size"])
                  for entry in item["files"]}
        found = {Path(entry["path"]).relative_to(destination).as_posix(): (entry["sha256"], entry["size"])
                 for entry in actual["files"]}
        wanted_dirs = {Path(name).relative_to(item["source"]).as_posix() for name in item["directories"]}
        found_dirs = {Path(name).relative_to(destination).as_posix() for name in actual["directories"]}
        if any(entry["reason"] != "system_metadata" for entry in actual["excluded"]) or wanted != found or wanted_dirs != found_dirs:
            raise Stop("コピー先の全件照合が一致しません。本人編集は上書きしません")


def perform(plan, source, workspace, journal):
    validate_plan(plan, source, workspace)
    pending = journal.get("pending_file")
    if pending:
        matches = [(item, entry) for item in plan["projects"] for entry in item["files"]
                   if entry["path"] == pending.get("source")]
        if len(matches) != 1:
            raise Stop("中断ファイルが計画と一致しません")
        copy_file(plan, *matches[0], workspace, journal)
    for item in plan["projects"]:
        destination = item["destination"]
        target = checked(workspace, destination)
        if destination not in journal["owned"]:
            if os.path.lexists(target):
                raise Stop("作成前のコピー先に別のフォルダがあります")
            journal["owned"].append(destination)
            save_journal(workspace, journal)
        ensure_directory(workspace, destination)
        expected = {}
        for entry in item["files"]:
            suffix = Path(entry["path"]).relative_to(item["source"]).as_posix()
            expected[suffix] = entry
        destination_includes = [destination + "/" + Path(name).relative_to(item["source"]).as_posix()
                                for name in plan["includes"] if name.startswith(item["source"] + "/")]
        actual = inventory(workspace, destination, destination_includes)
        actual_names = {Path(entry["path"]).relative_to(destination).as_posix() for entry in actual["files"]}
        if any(entry["reason"] != "system_metadata" for entry in actual["excluded"]) or actual_names - expected.keys():
            raise Stop("コピー先に計画外のファイル・リンクがあります。保持して停止します")
        for directory in item["directories"]:
            suffix = Path(directory).relative_to(item["source"]).as_posix()
            ensure_directory(workspace, destination + "/" + suffix)
        for suffix, entry in expected.items():
            dest = destination + "/" + suffix
            path = checked(workspace, dest)
            if os.path.lexists(path):
                if fingerprint(workspace, dest)["sha256"] != entry["sha256"]:
                    raise Stop("途中のコピー先に変更があります。上書きしません: " + dest)
            else:
                copy_file(plan, item, entry, workspace, journal)
            if fingerprint(workspace, dest)["sha256"] != entry["sha256"]:
                raise Stop("コピー照合が一致しません")
    validate_plan(plan, source, workspace)
    verify_copy(plan, workspace)
    journal["phase"] = "wiki"
    save_journal(workspace, journal)
    for path, change in plan["wiki"].items():
        checked(workspace, path)
        actual = digest(read(workspace, path)) if (workspace / path).exists() else None
        desired = change["after"].encode()
        if actual == digest(desired):
            continue
        if actual != change["before"]:
            raise Stop("Wikiに追加編集があります。上書きしません")
        replace_file(workspace, path, desired)
    validate_plan(plan, source, workspace)
    for path, change in plan["wiki"].items():
        if digest(read(workspace, path)) != digest(change["after"].encode()):
            raise Stop("Wikiの更新が未完了です")
    verify_copy(plan, workspace)
    completion = module("wiki_view").audit_migration_completion(workspace)
    touched = set(plan["wiki"])
    baseline = {encoded(entry) for entry in plan["existing_findings"]}
    findings = [entry for entry in completion["findings"] if entry.get("page") in touched and encoded(entry) not in baseline]
    if findings:
        raise Stop("Wikiの移行完了点検に残件があります: " + json.dumps(findings, ensure_ascii=False))
    journal["phase"] = "complete"
    save_journal(workspace, journal)
    return {"status": "complete", "plan": plan["id"], "projects": len(plan["projects"]),
            "files": sum(len(item["files"]) for item in plan["projects"]),
            "runtime": "not_checked", "git": "not_saved", "source": "unchanged_by_tool",
            "completion_findings": findings, "existing_findings": plan["existing_findings"],
            "completion_advisories": completion["advisories"]}


def probe_hardlinks(workspace, plan):
    import tempfile
    staging = ensure_directory(workspace, STATE + "/staging")
    for item in plan["projects"]:
        parent = checked(workspace, item["destination"]).parent
        while not parent.exists():
            parent = parent.parent
        if parent.stat().st_dev != staging.stat().st_dev:
            raise Stop("案件の保存先と内部状態が別のディスクです。安全なhardlinkコピーができないため、案件・中断記録は作成していません")
    with tempfile.TemporaryDirectory(prefix="link-probe-", dir=staging) as temporary:
        original = Path(temporary) / "source"
        original.write_bytes(b"output-migration-probe")
        try:
            os.link(original, Path(temporary) / "linked")
        except OSError as error:
            raise Stop("保存先は安全な一括コピーに必要なhardlinkに対応していません。案件・中断記録は作成していません") from error


@contextmanager
def operation_lock(workspace):
    ensure_directory(workspace, STATE)
    path = checked(workspace, STATE + "/process.guard")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o600)
    acquired = False
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or linked(info):
            raise Stop("処理の排他記録が通常ファイルではありません")
        if info.st_size == 0:
            os.write(descriptor, b"0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as error:
            raise Stop("別のコピー・復旧処理が稼働中です") from error
        yield
    finally:
        if acquired:
            if os.name == "nt":
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def recover_lock(workspace, plan_id=None):
    with operation_lock(workspace):
        recover_lock_owned(workspace, plan_id)


def recover_lock_owned(workspace, plan_id=None):
    lock_path = STATE + "/apply.lock"
    if os.path.lexists(checked(workspace, lock_path)):
        lock = json.loads(read(workspace, lock_path))
        if (not isinstance(lock, dict) or not re.fullmatch(r"[a-f0-9]{64}", str(lock.get("plan", ""))) or
                (plan_id is not None and lock["plan"] != plan_id) or type(lock.get("pid")) is not int):
            raise Stop("ロックの所有者を確認できません。自動削除しません")
        migration = module("migrate_v3")
        try:
            alive = migration.pid_alive(lock["pid"])
        except migration.Stop as error:
            raise Stop("ロックの所有者を確認できません。保持して停止します") from error
        if alive:
            raise Stop("コピー処理が稼働中か所有者を確認できません")
        checked(workspace, lock_path).unlink()


def execute(plan, source, workspace, resume=False):
    validate_plan(plan, source, workspace)
    if not plan["projects"]:
        return {"status": "nothing_to_copy", "read_only": True, "already_copied": plan["already_copied"]}
    with operation_lock(workspace):
        return execute_owned(plan, source, workspace, resume)


def execute_owned(plan, source, workspace, resume):
    journal = load_journal(workspace) if resume else None
    ensure_directory(workspace, STATE)
    lock_path = STATE + "/apply.lock"
    recover_lock_owned(workspace, plan["id"] if resume else None)
    owner = encoded({"pid": os.getpid(), "plan": plan["id"], "token": os.urandom(16).hex()})
    write_new(workspace, lock_path, owner, 0o600)
    try:
        journal_path = STATE + "/transaction.json"
        if resume:
            if journal["plan"] != plan:
                raise Stop("再開記録と計画が一致しません")
        else:
            if os.path.lexists(checked(workspace, journal_path)):
                previous = load_journal(workspace)
                if previous.get("phase") != "complete":
                    raise Stop("一括コピーが中断しています。resumeで確認してください")
                archive = STATE + "/" + previous["plan"]["id"] + ".json"
                if not os.path.lexists(checked(workspace, archive)):
                    archived = {key: value for key, value in previous.items() if key != "plan"}
                    write_new(workspace, archive, encoded(archived), 0o600)
            probe_hardlinks(workspace, plan)
            plan_path = STATE + "/plans/" + plan["id"] + ".json"
            if os.path.lexists(checked(workspace, plan_path)):
                if read(workspace, plan_path, 128 * 1024 * 1024) != encoded(plan):
                    raise Stop("保存済み計画が一致しません")
            else:
                replace_file(workspace, plan_path, encoded(plan))
            journal = {"phase": "copying", "plan": plan, "owned": [], "pending_file": None}
            save_journal(workspace, journal)
        return perform(plan, source, workspace, journal)
    finally:
        if read(workspace, lock_path) != owner:
            raise Stop("lockの所有者が変わっています。削除せず停止します")
        checked(workspace, lock_path).unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("scan", "apply", "resume"))
    parser.add_argument("--from", dest="source", type=Path)
    parser.add_argument("--ws", type=Path, default=Path.cwd())
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--all", action="store_true")
    selection.add_argument("--project", action="append", default=[])
    parser.add_argument("--include-template", action="append", default=[])
    parser.add_argument("--plan")
    args = parser.parse_args()
    try:
        workspace = canonical(args.ws)
        if args.command == "resume":
            journal_path = STATE + "/transaction.json"
            if not os.path.lexists(checked(workspace, journal_path)):
                lock_present = os.path.lexists(checked(workspace, STATE + "/apply.lock"))
                if args.plan:
                    recover_lock(workspace, args.plan)
                result = {"status": "empty", "read_only": not (args.plan and lock_present),
                          "lock_present": os.path.lexists(checked(workspace, STATE + "/apply.lock"))}
            else:
                journal = load_journal(workspace)
                plan = journal["plan"]
                if not args.plan:
                    result = {"status": journal["phase"], "plan": plan["id"], "read_only": True,
                              "lock_present": os.path.lexists(checked(workspace, STATE + "/apply.lock"))}
                elif args.plan != plan["id"]:
                    raise Stop("承認hashが再開計画と一致しません")
                elif journal["phase"] == "complete":
                    lock_present = os.path.lexists(checked(workspace, STATE + "/apply.lock"))
                    recover_lock(workspace, plan["id"])
                    result = {"status": "complete", "read_only": not lock_present, "plan": plan["id"], "lock_present": False}
                else:
                    result = execute(plan, Path(plan["source"]), workspace, resume=True)
        else:
            if args.source is None:
                raise Stop("--fromで移行元を指定してください")
            source = canonical(args.source)
            plan = make_plan(source, workspace, args.project, args.all, args.include_template)
            if args.command == "scan":
                result = public_plan(plan)
            else:
                if args.plan != plan["id"]:
                    raise Stop("承認hashが現在の計画と一致しません。scanを見せて再承認してください")
                result = execute(plan, source, workspace)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (Stop, OSError, ValueError, KeyError, UnicodeError, TypeError, AttributeError, RecursionError) as error:
        reason = ("ファイル操作に失敗しました（" + type(error).__name__ + "）。権限・空き容量・配置を確認し、resumeで中断状態を確認してください" if isinstance(error, OSError) else str(error))
        print(json.dumps({"status": "stopped", "reason": reason}, ensure_ascii=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

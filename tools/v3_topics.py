#!/usr/bin/env python3
"""Validate conversation-authored topic plans; never infer classifications."""
import copy
import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote

SCHEMA = 2
POLICY = "v3-topics-3"
ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
BEGIN = "<!-- os-topics:begin -->"
END = "<!-- os-topics:end -->"
KEYS = {"migration_session_id", "plan_phase", "batch_cursor", "schema_version",
        "policy_version", "base_plan_hash", "workspace_head", "input_manifest",
        "category_defs", "targets", "changes", "plan_hash"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def seal(plan):
    plan["plan_hash"] = digest(canonical({key: value for key, value in plan.items() if key != "plan_hash"}))
    return plan


class PlanGuidance(ValueError):
    pass


def fail(message):
    raise ValueError(message)


def relative(path):
    if not isinstance(path, str) or not path or "\\" in path or "<!-- os-topics:" in path or any(ord(char) < 32 for char in path):
        fail("invalid relative path")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts) or Path(path).is_absolute():
        fail("invalid relative path")
    if re.match(r"[a-zA-Z]:", path) or any(ord(char) == 127 for char in path):
        fail("invalid relative path")
    return path


def text(value):
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value or "<!-- os-topics:" in value:
        fail("nonempty single-line text required")
    if re.search(r"(?i)file:|(?:^|[^\w:/])/[^\s)]|[a-z]:[/\\]|\\\\|~[/\\]|\$(?:HOME|USERPROFILE)|%USERPROFILE%", value):
        fail("absolute paths must not be recorded")
    return value


class MetadataConflict(ValueError):
    pass


def conflict(path, key, value, issue):
    try:
        relative(path)
        safe_path = path
    except ValueError:
        safe_path = "（安全でない相対パスは非表示）"
    safe_key = key if re.fullmatch(r"[a-z_]{1,48}", key) else "（項目名非表示）"
    safe_value = value if re.fullmatch(r'[\[\]"a-z0-9, -]{0,100}', value) and not re.search(r"secret|token|password|sk-", value) else "（旧値は安全のため非表示・原文を保持）"
    raise MetadataConflict(f"{safe_path}: 項目 {safe_key}: {issue}; 旧値 {safe_value}。"
                           "自動変換せず承認前に停止しました。原文を保持した別差分で重複を解消し、"
                           'os_topics をJSON配列（例 ["booking"]）、os_topic_state を classified/pending に対応付け、'
                           "予約項目の別用途は退避案を本人承認してから再実行してください。block/flow YAML配列は自動変換しません。")


def metadata(data, path="unknown.md"):
    content = data.decode("utf-8")
    match = re.match(r"\A\ufeff?---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", content, re.S)
    result = {}
    if match:
        for line in match.group(1).splitlines():
            item = re.match(r"^([\w-]+):\s*(.*)$", line)
            if item:
                key, value = item.groups()
                if key in result:
                    conflict(path, key, result[key], "frontmatter項目の重複")
                result[key] = value
    return content, match, result


def scalar(value):
    if value.startswith('"') or value.startswith("["):
        return json.loads(value)
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value in ("", "|", ">"):
        fail("unsupported metadata value")
    return value


def assignments(data, path="unknown.md"):
    _, _, fields = metadata(data, path)
    reserved = {key for key in fields if key.startswith("os_topic")}
    if reserved - {"os_topics", "os_topic_state"}:
        key = sorted(reserved - {"os_topics", "os_topic_state"})[0]
        conflict(path, key, fields[key], "予約項目の別用途との衝突")
    if not reserved:
        return None
    if reserved != {"os_topics", "os_topic_state"}:
        key = sorted(reserved)[0]
        conflict(path, key, fields[key], "所属と状態の組が不完全")
    try:
        topics = json.loads(fields["os_topics"])
        state = scalar(fields["os_topic_state"])
        validate_assignment(topics, state)
    except (ValueError, TypeError):
        conflict(path, "os_topics", fields["os_topics"], "JSON配列・安定ID・所属状態の契約に不適合")
    return topics, state


def validate_assignment(topics, state):
    if not isinstance(topics, list) or any(not isinstance(topic, str) or not ID.fullmatch(topic) for topic in topics):
        fail("os_topics must contain stable IDs")
    if len(topics) != len(set(topics)) or state not in ("classified", "pending"):
        fail("duplicate topic or invalid state")
    if bool(topics) != (state == "classified"):
        fail("state and memberships disagree")


def patch_metadata(data, topics, state):
    assignments(data)
    content, match, _ = metadata(data)
    newline = "\r\n" if match and "\r\n" in match.group(0) else "\n"
    added = ["os_topics: " + json.dumps(topics, ensure_ascii=False), "os_topic_state: " + state]
    prefix = "\ufeff" if content.startswith("\ufeff") else ""
    if not match:
        return (prefix + "---\n" + "\n".join(added) + "\n---\n" + content[len(prefix):]).encode()
    kept = [line for line in match.group(1).splitlines() if not re.match(r"^os_topics:|^os_topic_state:", line)]
    return (prefix + "---" + newline + newline.join(kept + added) + newline + "---" +
            (newline if match.group(0).endswith("\n") else "") + content[match.end():]).encode()


def region(data, generated, namespace="os-topics"):
    content = data.decode("utf-8")
    begin, end = "<!-- " + namespace + ":begin -->", "<!-- " + namespace + ":end -->"
    markers = re.findall(r"<!--\s*" + re.escape(namespace) + r"\b[^\n]*", content)
    if (content.count(begin) != content.count(end) or content.count(begin) > 1
            or any(marker not in (begin, end) for marker in markers)
            or any(line != marker for line in content.splitlines() for marker in (begin, end) if marker in line)):
        fail("generated entry region conflict")
    fence = None
    for line in content.splitlines():
        if fence is not None:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*", line):
                fence = None
        else:
            match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
            if match and (match[1][0] != "`" or "`" not in match[2]):
                fence = match[1]
        if line in (begin, end) and fence is not None:
            fail("generated entry region inside code fence")
    for code in re.finditer(r"(?<!`)(`+)(?!`)(.*?)(?<!`)\1(?!`)", content, re.S):
        if any(marker in code.group(0) for marker in (begin, end)):
            fail("generated entry region inside code span")
    html_content = re.sub(r"<!--.*?(?:-->|\Z)", lambda match: re.sub(r"[^\n]", " ", match[0]), content, flags=re.S)
    for code in re.finditer(r"<(pre|code|script|style|textarea)\b[^>]*>.*?(?:</\1\s*>|\Z)", html_content, re.I | re.S):
        if any(marker in content[code.start():code.end()] for marker in (begin, end)):
            fail("generated entry region inside HTML code")
        if begin not in content and not re.search(r"</" + code[1] + r"\s*>$", code.group(0), re.I):
            fail("cannot append entry inside unfinished HTML code")
    for comment in re.finditer(r"<!--.*?(?:-->|\Z)", content, re.S):
        if (any(marker in comment.group(0) for marker in (begin, end))
                and comment.group(0) not in (begin, end)):
            fail("generated entry region inside comment")
    replacement = begin + "\n" + generated + "\n" + end
    if begin in content:
        if content.index(begin) > content.index(end):
            fail("generated entry region order conflict")
        return (content[:content.index(begin)] + replacement + content[content.index(end) + len(end):]).encode()
    if fence is not None or content.rfind("<!--") > content.rfind("-->"):
        fail("cannot append entry inside unfinished markup")
    return (content + ("" if content.endswith("\n") else "\n") + "\n" + replacement + "\n").encode()


def planned_data(P, path, api, default=b""):
    api.safe_dest(P.ws, P.v3, path)
    if path in getattr(P, "writes", {}):
        return P.writes[path]
    if path in P.modifies:
        return P.modifies[path][1]
    return (P.ws / path).read_bytes() if os.path.lexists(P.ws / path) else default


def entry_link(label, path):
    text(label)
    return "- [" + re.sub(r"([\\`*_{}\[\]<>!|])", r"\\\1", label) + "](" + quote(path, safe="/.") + ")"


def markdown_destinations(content):
    from wiki_view import navigation_links

    destinations = navigation_links(content)
    return {(destination[2:] if destination.startswith("./") else destination).split("#", 1)[0]
            for destination in destinations}


def notes_entry(P, api, plan=None):
    path = "wiki/notes/index.md"
    data = planned_data(P, path, api, "# 知識の入口\n".encode())
    lines = []
    if plan is not None:
        lines = ["## 内容別カテゴリ"]
        lines += [entry_link(item["title"], "topics/" + item["id"] + ".md") + " — " +
                  re.sub(r"([\\`*_{}\[\]<>!|])", r"\\\1", item["scope"]) for item in plan["category_defs"]]
        lines += ["", "## 未分類・確認待ち"]
        lines += [entry_link(target["destination_path"], target["destination_path"][len("wiki/notes/"):])
                  for target in plan["targets"] if target["os_topic_state"] != "classified"]
    lines += ["", "## 来歴"]
    for label, target in (("v3 から移した知識", "v3/index.md"), ("移行の記録", "v3-migration.md")):
        destination = "wiki/notes/" + target
        if destination in P.writes or destination in P.modifies or os.path.lexists(P.ws / destination):
            api.safe_dest(P.ws, P.v3, destination)
            lines.append(entry_link(label, target))
    put(P, path, region(data, "\n".join(lines), "os-notes-navigation"), api)


def category(data, path):
    _, _, fields = metadata(data, path)
    required = {"os_topic_id", "title", "scope", "aliases"}
    if not required <= fields.keys():
        conflict(path, "os_topic_id", "", "カテゴリ定義に必要な項目が不足（通常文書ならカテゴリ定義の場所から退避する案を確認）")
    result = {key: scalar(fields[key]) for key in required}
    identity = result.pop("os_topic_id")
    if not isinstance(identity, str) or not ID.fullmatch(identity) or path != f"wiki/notes/topics/{identity}.md":
        fail("category ID/path conflict")
    result.update(id=identity, path=path, status="existing", before_hash=digest(data), after_hash=digest(data))
    validate_category(result)
    return result


def validate_category(item):
    if not isinstance(item, dict) or set(item) != {"id", "title", "scope", "aliases", "path", "status", "before_hash", "after_hash"}:
        fail("category schema mismatch")
    if not isinstance(item["id"], str) or not ID.fullmatch(item["id"]):
        fail("invalid category ID")
    if item["path"] != f"wiki/notes/topics/{item['id']}.md" or item["status"] not in ("existing", "new"):
        fail("invalid category path/status")
    for key in ("before_hash", "after_hash"):
        value = item[key]
        if value is None and item["status"] == "new":
            continue
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
            fail("invalid category hash")
    text(item["title"])
    text(item["scope"])
    if not isinstance(item["aliases"], list) or any(not isinstance(alias, str) for alias in item["aliases"]):
        fail("aliases must be a JSON array")
    for alias in item["aliases"]:
        text(alias)
    if len(item["aliases"]) != len(set(item["aliases"])):
        fail("duplicate aliases")


def workspace_files(P, api):
    result, manifest = {}, []
    root = P.ws / "wiki"
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs.sort()
        names.sort()
        for name in list(dirs):
            child = Path(current) / name
            if child.is_symlink():
                fail("wiki symlink directory")
        for name in names:
            path = Path(current) / name
            rel = path.relative_to(P.ws).as_posix()
            relative(rel)
            api.safe_dest(P.ws, P.v3, rel)
            if not path.is_file():
                fail("wiki non-regular input")
            data = path.read_bytes()
            excluded = api.is_secret_name(name)
            try:
                excluded = excluded or bool(api.secret_lines(data.decode("utf-8")))
            except UnicodeDecodeError:
                excluded = True
            manifest.append(dict(root="workspace", path=rel, sha256=digest(data), mode=path.stat().st_mode & 0o777,
                                 disposition="excluded" if excluded else "reference"))
            if not excluded and path.suffix == ".md":
                result[rel] = data
    return result, manifest


def snapshot(P, base_hash, api, session_id=None):
    files, manifest = workspace_files(P, api)
    categories = [category(data, path) for path, data in sorted(files.items()) if path.startswith("wiki/notes/topics/")]
    excluded = {"wiki/notes/index.md", "wiki/notes/v3/index.md", "wiki/notes/v3/recipes.md", "wiki/notes/v3/recipe-links.md", "wiki/notes/v3-migration.md"}
    targets, content = [], {}
    generated = {path: data for path, data in P.writes.items() if path in P.src_of and path.startswith("wiki/notes/v3/")}
    for path, data in sorted({**files, **generated}.items()):
        if not path.startswith("wiki/notes/") or path.startswith("wiki/notes/topics/"):
            continue
        actual_note = False
        if path == "wiki/notes/index.md":
            entry_content, _, fields = metadata(data, path)
            navigation = ("<!-- os-notes-navigation:begin -->" in entry_content
                          or ({"../index.md", "../README.md"} <= markdown_destinations(entry_content)
                              and "## 内容別カテゴリ" in entry_content and "## 来歴" in entry_content))
            actual_note = bool({"status", "os_topics", "os_topic_state"} & fields.keys()) or not navigation
        if path in excluded and not actual_note:
            continue
        if api.secret_lines(data.decode("utf-8")):
            continue
        previous = assignments(data, path)
        source = P.src_of.get(path, path)
        relative(path)
        relative(source)
        content[path] = data
        targets.append(dict(source_path=source, destination_path=path, input_hash=digest(data), evaluated=False,
                            previous_assignment=None if previous is None else dict(os_topics=previous[0], os_topic_state=previous[1]),
                            os_topics=[] if previous is None else previous[0],
                            os_topic_state=None if previous is None else previous[1], evidence=[], reason="", origin="ai"))
        manifest.append(dict(root="target", path=path, sha256=digest(data), mode=P.modes.get(path, 0o644),
                             disposition="target"))
    target_sources = {item["source_path"] for item in targets if item["destination_path"] in generated}
    for path, hash_value in sorted(P.read.items()):
        manifest.append(dict(root="v3", path=path, sha256=hash_value,
                             mode=(P.v3 / path).stat().st_mode & 0o777,
                             disposition="target_source" if path in target_sources else "excluded_from_classification"))
    manifest.sort(key=lambda item: (item["root"], item["path"]))
    head = api.git(P.ws, "rev-parse", "HEAD")
    if head.returncode or not head.stdout.strip():
        fail("workspace HEAD required")
    plan = dict(schema_version=SCHEMA, policy_version=POLICY,
                migration_session_id=session_id or uuid.uuid4().hex, plan_phase="intermediate", batch_cursor=0,
                base_plan_hash=base_hash, workspace_head=head.stdout.strip(), input_manifest=manifest,
                category_defs=categories, targets=targets, changes=[], plan_hash="")
    return seal(plan), content, files


def validate(P, base_hash, proposal, api, final=False):
    if not isinstance(proposal, dict) or set(proposal) != KEYS:
        fail("plan schema mismatch")
    session_id = proposal["migration_session_id"]
    if not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
        fail("invalid migration session ID")
    fresh, content, files = snapshot(P, base_hash, api, session_id)
    for key in ("schema_version", "policy_version", "base_plan_hash", "workspace_head", "input_manifest"):
        if proposal[key] != fresh[key] or type(proposal[key]) is not type(fresh[key]):
            if key == "base_plan_hash":
                raise PlanGuidance("stale or invalid base_plan_hash。元データかワークスペースが変わりました。hash を手で書き換えず、"
                                   "同じ --from / --to（補修なら --repair）と --classification を指定して refresh し、"
                                   "変更された対象を read で再確認 → evaluate → 本人の再承認へ進めてください。")
            fail("stale or invalid " + key)
    if proposal["plan_phase"] not in ("intermediate", "final"):
        fail("invalid plan phase")
    if not isinstance(proposal["category_defs"], list) or not isinstance(proposal["targets"], list):
        fail("categories/targets must be arrays")
    categories = proposal["category_defs"]
    identities = []
    existing = {item["id"]: item for item in fresh["category_defs"]}
    for item in categories:
        validate_category(item)
        identities.append(item["id"])
        if item["id"] in existing:
            if item != existing[item["id"]] and {key: value for key, value in item.items() if key != "after_hash"} != {key: value for key, value in existing[item["id"]].items() if key != "after_hash"}:
                fail("existing category definition changed")
        elif item["status"] != "new" or item["before_hash"] is not None:
            fail("new category must have null before_hash")
    if len(identities) != len(set(identities)) or not existing.keys() <= set(identities):
        fail("duplicate or missing category")
    targets = proposal["targets"]
    if len(targets) != len(fresh["targets"]):
        fail("target coverage mismatch")
    cursor = 0
    for position, (supplied, expected) in enumerate(zip(targets, fresh["targets"])):
        if not isinstance(supplied, dict) or set(supplied) != set(expected):
            fail("target schema mismatch")
        for key in ("source_path", "destination_path", "input_hash", "previous_assignment"):
            if supplied[key] != expected[key]:
                fail("target identity/order/hash mismatch")
        if type(supplied["evaluated"]) is not bool:
            fail("evaluated must be boolean")
        if not supplied["evaluated"]:
            if supplied != expected:
                fail("unevaluated target contains decisions")
            continue
        cursor += 1
        validate_assignment(supplied["os_topics"], supplied["os_topic_state"])
        if not set(supplied["os_topics"]) <= set(identities):
            fail("unknown category ID")
        text(supplied["reason"])
        if supplied["origin"] not in ("ai", "user"):
            fail("origin must be ai/user")
        evidence = supplied["evidence"]
        if not isinstance(evidence, list) or not evidence:
            fail("evidence line references required")
        lines = len(content[supplied["destination_path"]].decode().splitlines())
        for reference in evidence:
            if not isinstance(reference, dict) or set(reference) != {"start_line", "end_line"}:
                fail("evidence must identify line ranges, not copy source text")
            start, end = reference["start_line"], reference["end_line"]
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= lines:
                raise PlanGuidance(f"invalid evidence line range（対象 {position + 1}、有効範囲 1〜{lines} 行）。"
                                   "read の text を JSON デコードし、先頭を1行目として数えてください。"
                                   "元v3ではなく移行先の本文（frontmatter・空行を含む）の行番号を使います。")
    next_position = next((index for index, target in enumerate(targets) if not target["evaluated"]), len(targets))
    if type(proposal["batch_cursor"]) is not int or proposal["batch_cursor"] != next_position:
        fail("batch_cursor/evaluated mismatch")
    if (final or proposal["plan_phase"] == "final") and cursor != len(targets):
        fail("unevaluated targets cannot be applied")
    result = copy.deepcopy(proposal)
    if final:
        result["plan_phase"] = "final"
    if result["plan_phase"] == "final":
        bundle(P, result, content, files, api)
    else:
        result["changes"] = []
        for item in result["category_defs"]:
            if item["status"] == "new":
                item["after_hash"] = None
    if api.secret_lines(canonical(result).decode()):
        fail("secret-like classification data")
    return seal(result)


def refresh(P, base_hash, previous, api):
    if not isinstance(previous, dict) or set(previous) != KEYS or seal(copy.deepcopy(previous))["plan_hash"] != previous["plan_hash"]:
        fail("refresh requires a previously validated checkpoint")
    session_id = previous["migration_session_id"]
    if not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
        fail("invalid migration session ID")
    fresh, _, _ = snapshot(P, base_hash, api, session_id)
    old_categories = [dict(item, after_hash=item["before_hash"]) for item in previous["category_defs"] if item["status"] == "existing"]
    if sorted(old_categories, key=lambda item: item["id"]) == sorted(fresh["category_defs"], key=lambda item: item["id"]):
        fresh["category_defs"].extend(copy.deepcopy([item for item in previous["category_defs"] if item["status"] == "new"]))
        old_targets = {(item["source_path"], item["destination_path"], item["input_hash"]): item for item in previous["targets"] if item["evaluated"]}
        for position, new in enumerate(fresh["targets"]):
            old = old_targets.get((new["source_path"], new["destination_path"], new["input_hash"]))
            if old is not None:
                fresh["targets"][position] = copy.deepcopy(old)
        fresh["batch_cursor"] = next((index for index, target in enumerate(fresh["targets"]) if not target["evaluated"]), len(fresh["targets"]))
    return validate(P, base_hash, fresh, api)


def put(P, path, data, api):
    relative(path)
    api.safe_dest(P.ws, P.v3, path)
    if path in getattr(P, "writes", {}):
        P.writes[path] = data
    elif path in P.modifies:
        original = P.modifies[path][0]
        if original == data:
            del P.modifies[path]
        else:
            P.modifies[path] = (original, data)
    elif os.path.lexists(P.ws / path):
        original = (P.ws / path).read_bytes()
        if original != data:
            P.modifies[path] = (original, data)
    else:
        P.new(path, data, mode=0o644)


def bundle(P, plan, content, files, api):
    for target in plan["targets"]:
        path = target["destination_path"]
        put(P, path, patch_metadata(content[path], target["os_topics"], target["os_topic_state"]), api)
    for item in plan["category_defs"]:
        path = item["path"]
        if item["status"] == "existing":
            data = files[path]
        else:
            if os.path.lexists(P.ws / path) or path in P.writes:
                fail("category destination collision")
            fields = [("os_topic_id", item["id"]), ("title", item["title"]),
                      ("scope", item["scope"]), ("aliases", item["aliases"])]
            data = ("---\n" + "\n".join(key + ": " + json.dumps(value, ensure_ascii=False) for key, value in fields) + "\n---\n").encode()
        members = [target for target in plan["targets"] if item["id"] in target["os_topics"]]
        links = ["- [" + re.sub(r"([\\`*_{}\[\]<>!|])", r"\\\1", target["destination_path"]) + "](" +
                 quote(os.path.relpath(target["destination_path"], "wiki/notes/topics"), safe="/.") + ")" for target in members]
        data = region(data, "\n".join(links) or "所属する知識はまだありません。")
        item["after_hash"] = digest(data)
        put(P, path, data, api)
    ledger = ["分類計画: " + plan["migration_session_id"], "分類時点: " + api.TODAY,
              "分類確認待ちがある場合は移行完了ではありません。resume で継続対象を確認してください。", ""]
    for target in plan["targets"]:
        refs = ",".join(str(item["start_line"]) + "-" + str(item["end_line"]) for item in target["evidence"])
        ledger.append("- " + json.dumps({"path": target["destination_path"], "state": target["os_topic_state"],
                                      "topics": target["os_topics"], "reason": target["reason"],
                                      "origin": target["origin"], "evidence_lines": refs}, ensure_ascii=False))
    path = "wiki/notes/v3-migration.md"
    data = P.writes.get(path, files.get(path))
    if data is None:
        data = b"---\ntitle: v3 migration topics\nstatus: draft\n---\n"
    put(P, path, region(data, "\n".join(ledger)), api)
    notes_entry(P, api, plan)
    plan["changes"] = []
    for path in sorted(set(P.writes) | set(P.modifies)):
        before, after = (None, P.writes[path]) if path in P.writes else P.modifies[path]
        mode = P.modes.get(path, (P.ws / path).stat().st_mode & 0o777 if before is not None else 0o644)
        plan["changes"].append(dict(path=path, before_hash=digest(before) if before is not None else None,
                                    after_hash=digest(after), mode=mode, kind="create" if before is None else "modify"))


def summary(plan):
    names = {}
    for item in plan["category_defs"]:
        for name in {item["title"], *item["aliases"]}:
            names.setdefault(name.casefold(), set()).add(item["id"])
    return dict(categories=[dict(id=item["id"], title=item["title"], aliases=item["aliases"], status=item["status"],
                                 memberships=sum(item["id"] in target["os_topics"] for target in plan["targets"]))
                            for item in plan["category_defs"]],
                overlapping_names=[dict(name=name, ids=sorted(ids)) for name, ids in sorted(names.items()) if len(ids) > 1],
                assignment_diff=[dict(path=target["destination_path"], before=target["previous_assignment"],
                                      after=dict(os_topics=target["os_topics"], os_topic_state=target["os_topic_state"]),
                                      evaluated=target["evaluated"], reason=target["reason"])
                                 for target in plan["targets"]],
                limitations="名前の意味的重複と origin=user の本人指定根拠は技術保証せず、AI/本人の確認が必要です。")


def session_dir(ws, api):
    response = api.git(ws, "rev-parse", "--absolute-git-dir")
    if response.returncode:
        fail("workspace git directory unavailable")
    return Path(response.stdout.strip()) / "v3-topics"


def save(plan, ws, api):
    directory = session_dir(ws, api)
    if directory.is_symlink():
        fail("session directory symlink")
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / (plan["migration_session_id"] + ".json")
    api.durable_json(path, plan)
    return path


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)


def resume(ws, api):
    directory = session_dir(ws, api)
    results = []
    if not directory.exists():
        return results
    if directory.is_symlink():
        fail("session directory symlink")
    if (directory / "transaction.json").exists() or (directory / "apply.lock").exists():
        results.append(dict(recovery_required=True, command="recover --plan <承認hash>",
                            message="中断記録を確認し、本人編集がなければ対象だけを復旧します。ロックを手動削除しないでください。"))
        return results
    probe = api.Plan(ws / "imports", ws)
    current_files, current_manifest = workspace_files(probe, api)
    for path in sorted(directory.glob("*.json")):
        if not re.fullmatch(r"[a-f0-9]{32}\.json", path.name):
            continue
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                fail("unsafe saved session")
            plan = load(path)
            if not isinstance(plan, dict) or set(plan) != KEYS or seal(copy.deepcopy(plan))["plan_hash"] != plan["plan_hash"]:
                fail("invalid saved session")
        except (OSError, ValueError, TypeError):
            results.append(dict(session_file=path.name, invalid_session=True,
                                message="保存済み計画が破損または安全に読めません。この計画は再利用せず、保存済みの写しと照合してください。"))
            continue
        applied = api.git(ws, "log", "--format=%H", "--fixed-strings", "--grep=計画の番号: " + plan["plan_hash"]).stdout.strip()
        pending = 0
        for target in plan["targets"]:
            if target["os_topic_state"] != "pending":
                continue
            current = current_files.get(target["destination_path"])
            assignment = assignments(current, target["destination_path"]) if current is not None else None
            if not applied or assignment is None or assignment[1] != "classified":
                pending += 1
        if not applied or pending:
            previous_manifest = [item for item in plan["input_manifest"] if item["root"] == "workspace"]
            workspace_stale = previous_manifest != sorted(current_manifest, key=lambda item: item["path"])
            results.append(dict(migration_session_id=plan["migration_session_id"], plan_phase=plan["plan_phase"],
                                batch_cursor=plan["batch_cursor"], total=len(plan["targets"]), pending=pending,
                                applied=bool(applied), stale=workspace_stale or api.git(ws, "rev-parse", "HEAD").stdout.strip() != plan["workspace_head"],
                                source_recheck_required=any(item["root"] == "v3" for item in plan["input_manifest"]),
                                session_file=str(path)))
    return results

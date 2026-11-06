#!/usr/bin/env python3
"""標準の継続案件を読み取り専用で静的検査する。試験やAIは実行しない。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

try:
    import tomllib
except ImportError:
    tomllib = None


LIMIT = 1024 * 1024
TEMPLATES = Path(__file__).resolve().parent / "building/templates"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(root, relative):
    parts = relative.split("/")
    require(all(part not in {"", ".", ".."} for part in parts)
            and not relative.startswith("/") and "\\" not in relative, "案件外の参照です")
    path = root
    for part in parts:
        path = path / part
        info = os.lstat(path)
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "リンク・再解析ポイントは検査しません")
    before = os.lstat(path)
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= LIMIT,
            "通常ファイル/大きさを確認できません")
    parents = [(parent, os.lstat(parent)) for parent in path.parents] if os.name == "nt" else []
    require(all(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400
                for parent, info in parents), "リンク・再解析ポイントは検査しません")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= LIMIT,
                "通常ファイル/大きさを確認できません")
        after = os.lstat(path)
        require(info.st_ino and os.path.samestat(before, info) and os.path.samestat(info, after)
                and not stat.S_ISLNK(after.st_mode) and not getattr(after, "st_file_attributes", 0) & 0x400
                and all(os.path.samestat(state, os.lstat(parent))
                        and not getattr(os.lstat(parent), "st_file_attributes", 0) & 0x400
                        for parent, state in parents), "検査対象が変更されました")
        content = stream.read(LIMIT + 1)
    require(len(content) <= LIMIT, "検査対象の大きさが不正です")
    return content


def unique_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "JSONに重複キーがあります")
            result[key] = value
        return result
    return json.loads(content, object_pairs_hook=pairs,
                      parse_constant=lambda value: require(False, "JSON定数が不正です"))


def text(root, relative):
    value = read(root, relative).decode("utf-8-sig")
    require(value.strip() and "\0" not in value and not re.search(r"\{\{[^}]+\}\}", value),
            "空の文書か未記入の雛形です")
    return value


def skill_tree(root, relative):
    directory = root / relative
    current = root
    for component in relative.split("/"):
        current = current / component
        require(not current.is_symlink(), "スキルの入口にリンクがあります")
    require(directory.is_dir() and not directory.is_symlink(), "スキルがありません")
    result = {}
    total = 0
    for parent, directories, files in os.walk(directory, followlinks=False):
        require(not any((Path(parent) / name).is_symlink()
                        or getattr(os.lstat(Path(parent) / name), "st_file_attributes", 0) & 0x400
                        for name in directories),
                "スキルにリンクがあります")
        for name in sorted(files):
            path = (Path(parent) / name).relative_to(root).as_posix()
            content = read(root, path)
            total += len(content)
            require(len(result) < 256 and total <= 8 * LIMIT, "スキルが大きすぎます")
            result[(Path(parent) / name).relative_to(directory).as_posix()] = hashlib.sha256(content).hexdigest()
    body = text(root, relative + "/SKILL.md")
    require(body.startswith("---\n") and "\n---" in body[4:], "スキルのfrontmatterがありません")
    header = body[4:].split("\n---", 1)[0]
    for field in ("name", "description"):
        values = re.findall(r"^" + field + r":\s*(\S[^\n]*)$", header, re.M)
        require(len(values) == 1 and values[0].strip() not in {"|", ">", "''", '""'},
                "スキルの名前/説明がありません（標準検査は1行形式のみ）")
    return result


def inspect_project(root):
    errors, warnings = [], ["静的検査のみ。実効権限・AI読込・試験成功は認定しません。"]
    root = Path(root).absolute()
    require(root.is_dir() and not any(path.is_symlink() for path in (root, *root.parents)),
            "案件ルートにリンクがあります")
    contract = unique_json(read(root, "build-contract.json"))
    require(isinstance(contract, dict) and set(contract) == {"schema", "methods", "ai", "skills", "checks"}
            and type(contract["schema"]) is int and contract["schema"] == 1, "契約の形式が不正です")
    for field in ("methods", "ai", "skills"):
        values = contract[field]
        require(isinstance(values, list) and len(values) <= 100
                and all(isinstance(value, str) for value in values)
                and len(values) == len(set(values)), "契約の配列が不正です")
    require(set(contract["ai"]) <= {"claude", "codex"}, "対応AIが不正です")
    require("project-setup@1" in contract["methods"]
            and all(re.fullmatch(r"[a-z][a-z0-9-]*@[1-9][0-9]*", value) for value in contract["methods"]),
            "共通手順のID/版が不正です")
    require(all(re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value) for value in contract["skills"]),
            "スキルIDが不正です")
    require(not contract["skills"] or contract["ai"], "スキルの対象AIがありません")

    def check(label, action):
        try:
            return action()
        except (OSError, ValueError, UnicodeError, RecursionError):
            errors.append(label + ": 内容/構文/参照先/標準安全項目を確認できません")
            return None

    check("README.md", lambda: text(root, "README.md"))
    if contract["ai"]:
        check("AGENTS.md", lambda: text(root, "AGENTS.md"))
        require("agent-settings@1" in contract["methods"], "設定手順の版がありません")

    if "claude" in contract["ai"]:
        check("CLAUDE.md", lambda: require("@AGENTS.md" in text(root, "CLAUDE.md").splitlines(),
                                          "共通入口への参照がありません"))

        def claude_settings():
            settings = unique_json(read(root, ".claude/settings.json"))
            baseline = unique_json(read(TEMPLATES, "claude-settings.json"))["permissions"]
            require(isinstance(settings, dict) and isinstance(settings.get("permissions"), dict), "設定型が不正です")
            permissions = settings["permissions"]
            for field in ("deny", "ask"):
                values = permissions.get(field)
                require(isinstance(values, list) and all(isinstance(value, str) for value in values)
                        and set(baseline[field]) <= set(values), "標準安全項目が不足しています")
            for field in ("deny", "ask", "allow"):
                rules = permissions.get(field, [])
                require(isinstance(rules, list) and all(isinstance(rule, str) for rule in rules), "権限規則の型が不正です")
                require(not any(re.match(r"\s*(?:Read|Edit)\(\s*!", rule) for rule in rules),
                        "否定規則による例外は標準安全検査で認定しません")
            require(permissions.get("defaultMode", "default") not in {"bypassPermissions", "dontAsk"},
                    "標準外の承認方式です")
            sandbox = settings.get("sandbox", {})
            standard = unique_json(read(TEMPLATES, "claude-settings.json"))["sandbox"]
            for key in ("enabled", "failIfUnavailable", "autoAllowBashIfSandboxed", "allowUnsandboxedCommands"):
                require(sandbox.get(key) is standard[key], "Claude sandboxの標準安全項目が異なります")
            filesystem = sandbox.get("filesystem", {})
            require(isinstance(filesystem, dict), "sandbox.filesystemの型が不正です")
            for field in ("denyRead", "denyWrite"):
                values = filesystem.get(field, [])
                require(isinstance(values, list) and all(isinstance(rule, str) for rule in values), "sandboxの拒否規則の型が不正です")
                require(not any(re.match(r"\s*!", rule) for rule in values), "sandboxの否定規則は標準安全検査で認定しません")
            require(set(standard["filesystem"]["denyRead"]) <= set(filesystem.get("denyRead", [])),
                    "Claude sandboxの秘密保護項目が不足しています")
            additional = set(sandbox) - set(standard)
            additional |= {"filesystem." + key for key in set(filesystem) - set(standard["filesystem"]) - {"denyWrite"}}
            if additional:
                warnings.append("sandboxの追加設定は未点検です: " + "、".join(sorted(additional)))
            credentials = sandbox.get("credentials", {})
            values = credentials.get("envVars", []) if isinstance(credentials, dict) else []
            require(isinstance(values, list), "環境変数保護の型が不正です")
            for protected in standard["credentials"]["envVars"]:
                entries = [entry for entry in values if isinstance(entry, dict) and entry.get("name") == protected["name"]]
                require(entries == [protected], "環境変数の標準denyが欠けるか重複/変更されています: " + protected["name"])
            require(not sandbox.get("excludedCommands"), "sandbox外のコマンドがあります")
            if (set(settings) - {"permissions", "sandbox"} or set(permissions) - {"deny", "ask"}):
                warnings.append("Claudeの追加設定（hooks/allow/追加範囲/承認方式等）は別の権限点検が必要です。")
        check(".claude/settings.json", claude_settings)
    if "codex" in contract["ai"]:
        def codex_settings():
            require(tomllib is not None, "Python 3.11以上が必要です")
            settings = tomllib.loads(read(root, ".codex/config.toml").decode("utf-8"))
            require(isinstance(settings.get("sandbox_workspace_write"), dict), "設定の型が不正です")
            require(set(settings["sandbox_workspace_write"]) == {"network_access"},
                    "標準外の書込範囲/サンドボックス設定です")
            require(settings.get("approval_policy") == "on-request"
                    and settings.get("sandbox_mode") == "workspace-write"
                    and settings.get("web_search") == "disabled"
                    and settings.get("sandbox_workspace_write", {}).get("network_access") is False,
                    "標準安全項目が異なります")
            if set(settings) - {"approval_policy", "sandbox_mode", "web_search", "sandbox_workspace_write"}:
                warnings.append("Codexの追加設定は別の権限・通信・hooks点検が必要です。")
        check(".codex/config.toml", codex_settings)
    for skill in contract["skills"]:
        trees = []
        for vendor in contract["ai"]:
            relative = (".agents" if vendor == "codex" else ".claude") + "/skills/" + skill
            trees.append(check(relative, lambda relative=relative: skill_tree(root, relative)))
        if len(trees) == 2 and all(tree is not None for tree in trees) and trees[0] != trees[1]:
            errors.append("共通スキル " + skill + ": 全ファイルが一致しません")
    checks = contract["checks"]
    require(isinstance(checks, list) and len(checks) <= 100, "試験記録が不正です")
    for entry in checks:
        require(isinstance(entry, dict) and set(entry) == {"name", "status", "evidence"}
                and isinstance(entry["name"], str) and entry["name"].strip()
                and isinstance(entry["status"], str) and entry["status"] in {"pass", "fail", "unrun"}
                and isinstance(entry["evidence"], str)
                and re.fullmatch(r"[A-Za-z0-9_/-]+\.md", entry["evidence"]), "試験記録の型/証拠パスが不正です")
        check("試験証拠", lambda entry=entry: text(root, entry["evidence"]))
    recorded_pass = bool(checks) and all(entry["status"] == "pass" for entry in checks)
    if not recorded_pass:
        warnings.append("試験記録が空か、未実施/不合格があります。完成扱いしません。")
    return {"static_pass": not errors, "recorded_checks_all_pass": recorded_pass,
            "errors": errors, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = inspect_project(args.project)
    except (OSError, ValueError, UnicodeError, RecursionError):
        result = {"static_pass": False, "recorded_checks_all_pass": False,
                  "errors": ["案件/契約の形式・型・参照先を確認できません"], "warnings": []}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["static_pass"] else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

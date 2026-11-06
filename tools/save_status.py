#!/usr/bin/env python3
"""Read-only, offline save diagnostics. Never print Git errors or file contents."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys


TIMEOUT = 5
MAX_ENTRIES = 20000
MAX_HEADER = 16384
OID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")


class Unchecked(Exception):
    """Only fixed, public reason codes may be passed here."""


def relative_path(value):
    if (not value or value.startswith(("/", "~", "-")) or
            any(ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value or ":" in value):
        raise Unchecked("invalid_relative_path")
    parts = value.split("/")
    if any(p.casefold() in ("", ".", "..", ".git") for p in parts):
        raise Unchecked("invalid_relative_path")
    return PurePosixPath(value).as_posix()


def label(value):
    # Paths are optional display hints, never used again as command arguments.
    if (len(value) > 160 or not re.fullmatch(r"[\w./-]+", value) or
            re.search(r"(?i)(gh[pousr]_|github_pat_|sk[-_]|akia)", value)):
        return "[非表示]"
    return value


def checked_path(path, boundary=None):
    """Check lexical containment before touching a path; never resolve links."""
    # Preserve '..' until each preceding component has been checked. abspath()
    # would erase 'link/..' even though Git follows that link in its gitdir file.
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if boundary is not None and not path.is_relative_to(boundary):
        raise Unchecked("outside_workspace")
    start = boundary if boundary is not None else Path(path.anchor)
    current = start
    for part in (None, *path.relative_to(start).parts):
        if part is not None:
            current = current.parent if part == ".." else current / part
        if boundary is not None and not current.is_relative_to(boundary):
            raise Unchecked("outside_workspace")
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            raise Unchecked("missing") from None
        except OSError:
            raise Unchecked("filesystem_unavailable") from None
        if stat.S_ISLNK(mode) or (hasattr(current, "is_junction") and current.is_junction()):
            raise Unchecked("symlink_not_followed")
    return current


def read_small(path, limit=MAX_HEADER):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise Unchecked("not_regular_file")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise Unchecked("metadata_too_large")
    try:
        return data.decode("utf-8")
    except UnicodeError:
        raise Unchecked("invalid_metadata") from None


def registration(path):
    """Read only the existing front matter, never a project's prose/body."""
    lines, size = [], 0
    with path.open("rb", buffering=0) as stream:
        if stream.readline(128).strip() != b"---":
            return None
        while True:
            raw = stream.readline(MAX_HEADER + 1)
            size += len(raw)
            if not raw or size > MAX_HEADER:
                raise Unchecked("invalid_registration")
            if raw.strip() == b"---":
                break
            lines.append(raw.decode("utf-8"))
    found = [line[5:].strip() for line in lines if line.startswith("path:")]
    if not found:
        return None
    if len(found) != 1:
        raise Unchecked("invalid_registration")
    value = found[0]
    # Support the single-line scalars used by wiki/README.md, not arbitrary YAML.
    if value.startswith('"'):
        try:
            value, end = json.JSONDecoder().raw_decode(value)
            tail = found[0][end:].strip()
            if tail and not tail.startswith("#"):
                raise ValueError
        except ValueError:
            raise Unchecked("invalid_registration") from None
    elif value.startswith("'"):
        match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", value)
        if not match:
            raise Unchecked("invalid_registration")
        value = match[1].replace("''", "'")
    else:
        value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
    if not isinstance(value, str) or value in ("|", ">", "[]", "{}"):
        raise Unchecked("invalid_registration")
    return value or None


def registered_projects(ws):
    directory = checked_path(ws / "wiki/projects", ws)
    if not directory.is_dir():
        raise Unchecked("registration_directory_unavailable")
    result = []
    for page in sorted(directory.iterdir()):
        if page.suffix != ".md" or page.name in ("index.md", "README.md"):
            continue
        if len(result) >= MAX_ENTRIES:
            raise Unchecked("too_many_registrations")
        item = {"page": label(page.relative_to(ws).as_posix())}
        try:
            checked_path(page, ws)
            if not page.is_file():
                continue
            value = registration(page)
            if value is None:
                continue
            item["raw_path"] = value
            item["path"] = "[非表示]"
            relative_path(value)
            item["path"] = label(value)
        except (OSError, UnicodeError):
            item["error"] = "registration_unavailable"
        except Unchecked as exc:
            item["error"] = str(exc)
        result.append(item)
    return result


def inventory(root):
    """Count existence only; don't read contents, follow links, or enter Git dirs."""
    counts = {"state": "present", "files": 0, "symlinks_not_followed": 0}
    stack, visited = [root], 0
    try:
        while stack:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    if entry.name == ".git":
                        continue
                    visited += 1
                    if visited > MAX_ENTRIES:
                        counts["state"] = "partial_limit"
                        return counts
                    if entry.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(entry.path)):
                        counts["symlinks_not_followed"] += 1
                    elif entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        counts["files"] += 1
    except OSError:
        counts["state"] = "filesystem_unavailable"
    return counts


class Git:
    def __init__(self):
        self.executable = shutil.which("git")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update({
            "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_NO_LAZY_FETCH": "1", "GIT_ATTR_NOSYSTEM": "1", "LC_ALL": "C",
        })

    def run(self, root, *args, allowed=(0,)):
        if not self.executable:
            raise Unchecked("git_unavailable")
        command = [self.executable, "--no-pager", "--no-optional-locks", "--literal-pathspecs"]
        if args[0] == "config":
            # Parse this one file without repository discovery (core.worktree and
            # included config must not be followed during the preflight itself).
            command += ["--git-dir=" + os.devnull]
        for setting in ("core.fsmonitor=false", "core.hooksPath=" + os.devnull,
                        "core.untrackedCache=false", "core.splitIndex=false", "gc.auto=0",
                        "maintenance.auto=false", "core.attributesFile=" + os.devnull,
                        "core.excludesFile=" + os.devnull):
            command += ["-c", setting]
        command += ["-C", str(root), *args]
        try:
            process = subprocess.run(command, env=self.env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            raise Unchecked("git_timeout") from None
        except FileNotFoundError:
            raise Unchecked("git_unavailable") from None
        except OSError:
            raise Unchecked("git_execution_unavailable") from None
        if process.returncode not in allowed:
            # Inspect only to classify. Do not retain or print stderr/stdout.
            reason = ("ownership_unavailable" if b"dubious ownership" in process.stderr
                      or b"unsafe repository" in process.stderr else "git_failed")
            raise Unchecked(reason)
        return process.returncode, process.stdout


def metadata_tree(root):
    """Git itself follows metadata links; reject them before invoking it."""
    stack, visited = [root], 0
    while stack:
        with os.scandir(stack.pop()) as entries:
            for entry in entries:
                visited += 1
                if visited > MAX_ENTRIES:
                    raise Unchecked("git_metadata_limit")
                if entry.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(entry.path)):
                    raise Unchecked("git_metadata_symlink")
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                elif not entry.is_file(follow_symlinks=False):
                    raise Unchecked("unsupported_git_metadata")


def git_layout(ws, root, git):
    marker = root / ".git"
    if not os.path.lexists(marker):
        for ancestor in root.parents:
            if not ancestor.is_relative_to(ws):
                break
            if os.path.lexists(ancestor / ".git"):
                return {"kind": "parent_repository_subfolder", "state": "not_independent"}
        return {"kind": "none", "state": "not_initialized"}
    result = {"kind": "directory" if stat.S_ISDIR(marker.lstat().st_mode) else "git_file"}
    try:
        checked_path(marker, ws)
        gitdir = marker
        if marker.is_file():
            pointer = read_small(marker, 4096).strip()
            if not pointer.startswith("gitdir: "):
                raise Unchecked("invalid_git_file")
            # An external gitdir is identified, but not followed, even for worktrees.
            gitdir = checked_path(root / pointer[8:], ws)
        if not gitdir.is_dir():
            raise Unchecked("invalid_git_directory")
        common = gitdir
        if os.path.lexists(gitdir / "commondir"):
            pointer = read_small(checked_path(gitdir / "commondir", ws), 4096).strip()
            if not pointer:
                raise Unchecked("invalid_git_file")
            common = checked_path(gitdir / pointer, ws)
            result["kind"] = "worktree"
        for directory in set((gitdir, common)):
            metadata_tree(directory)
            if (directory / "objects/info/alternates").exists() or (directory / "objects/info/http-alternates").exists():
                raise Unchecked("alternate_objects_unchecked")
            for name in ("config", "config.worktree"):
                config = directory / name
                if not config.exists():
                    continue
                _, keys = git.run(root, "config", "--no-includes", "--file", str(config),
                                  "--name-only", "--null", "--list")
                for key in keys.lower().split(b"\0"):
                    if (key.startswith((b"include.", b"includeif.", b"filter.")) or
                            key in (b"core.worktree", b"extensions.partialclone") or
                            (key.startswith(b"remote.") and key.endswith(b".promisor"))):
                        raise Unchecked("unsafe_config_unchecked")
        result["state"] = "ready"
    except Unchecked as exc:
        result["state"] = str(exc)
    return result


def git_status(ws, root, scope, git):
    result = git_layout(ws, root, git)
    if result["state"] != "ready":
        return result
    try:
        _, top = git.run(root, "rev-parse", "--show-toplevel")
        if Path(os.fsdecode(top).strip()) != root:
            raise Unchecked("repository_root_mismatch")
        _, bare = git.run(root, "rev-parse", "--is-bare-repository")
        if bare.strip() != b"false":
            raise Unchecked("bare_repository")
        rc, head = git.run(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}", allowed=(0, 1))
        if rc:
            symbolic, _ = git.run(root, "symbolic-ref", "--quiet", "HEAD", allowed=(0, 1))
            if symbolic:
                raise Unchecked("invalid_head")
            result["head"] = None
        else:
            result["head"] = head.decode("ascii").strip()
            if not OID.fullmatch(result["head"]):
                raise Unchecked("invalid_git_output")
        _, tracked = git.run(root, "ls-files", "--cached", "-z", "--", scope)
        result["tracked_entries"] = len([p for p in tracked.split(b"\0") if p])
        _, changes = git.run(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal",
                             "--ignored=matching", "--ignore-submodules=all", "--no-renames", "--", scope)
        counts = {"staged": 0, "unstaged": 0, "untracked": 0, "ignored": 0, "conflicted": 0}
        for record in changes.split(b"\0"):
            if not record:
                continue
            xy = record[:2]
            if len(record) < 4 or record[2:3] != b" ":
                raise Unchecked("invalid_git_output")
            if xy == b"??":
                counts["untracked"] += 1
            elif xy == b"!!":
                counts["ignored"] += 1
            else:
                counts["staged"] += xy[:1] != b" "
                counts["unstaged"] += xy[1:] != b" "
                counts["conflicted"] += b"U" in xy or xy in (b"AA", b"DD")
        result["changes"] = counts
        result["tracked_clean"] = not any(counts[k] for k in ("staged", "unstaged", "conflicted"))
        result["scope_last_commit"] = None
        result["upstream"] = {"state": "no_local_upstream"}
        if result["head"]:
            _, last = git.run(root, "log", "-1", "--no-show-signature", "--format=%H", "--", scope)
            last = last.decode("ascii").strip()
            if last and not OID.fullmatch(last):
                raise Unchecked("invalid_git_output")
            result["scope_last_commit"] = last or None
            rc, upstream = git.run(root, "rev-parse", "--verify", "--quiet", "@{upstream}^{commit}", allowed=(0, 1, 128))
            if not rc:
                if not OID.fullmatch(upstream.decode("ascii").strip()):
                    raise Unchecked("invalid_git_output")
                _, divergence = git.run(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}", "--")
                if not re.fullmatch(rb"\d+\s+\d+\s*", divergence):
                    raise Unchecked("invalid_git_output")
                ahead, behind = map(int, divergence.split())
                result["upstream"] = {"state": "local_ref_only", "ahead": ahead, "behind": behind}
        result["state"] = "checked" if result["head"] else "unborn"
        result["submodule_contents"] = "not_checked"
    except (UnicodeError, ValueError):
        result = {"kind": result["kind"], "state": "invalid_git_output"}
    except Unchecked as exc:
        result = {"kind": result["kind"], "state": str(exc)}
    return result


def inspect_target(ws, root, scope, git):
    result = {"external_backup": "not_checked_user_report_separate", "restore": "not_checked"}
    try:
        target = checked_path(root / scope, ws)
        if not target.is_dir():
            raise Unchecked("not_directory")
        result["files"] = inventory(target)
        if scope != "." and os.path.lexists(target / ".git"):
            result["git"] = {"kind": "nested_repository", "state": "parent_wiki_not_checked"}
        else:
            result["git"] = git_status(ws, root, scope, git)
    except Unchecked as exc:
        result["files"] = {"state": str(exc)}
        result["git"] = {"kind": "unknown", "state": "not_checked"}
    except OSError:
        result["git"] = {"kind": "unknown", "state": "filesystem_unavailable"}
    return result


def diagnose(ws_value, project=None):
    ws = checked_path(Path(ws_value))
    if not ws.is_dir():
        raise Unchecked("invalid_workspace")
    if project is not None:
        project = relative_path(project)
    projects = registered_projects(ws)
    if project is not None:
        projects = [p for p in projects if p.get("raw_path") == project and "error" not in p]
        if not projects:
            raise Unchecked("project_not_registered")
    git = Git()
    result = {"schema": 1, "mode": "read_only_offline", "wiki": inspect_target(ws, ws, "wiki", git), "projects": []}
    for item in projects:
        raw = item.pop("raw_path", None)
        if "error" in item:
            item["diagnostic"] = {"git": {"kind": "unknown", "state": "not_checked"},
                                  "files": {"state": item.pop("error")},
                                  "external_backup": "not_checked_user_report_separate", "restore": "not_checked"}
        else:
            item["diagnostic"] = inspect_target(ws, ws / raw, ".", git)
        result["projects"].append(item)
    return result


def render(result):
    if "error" in result:
        return "保存状況: 未確認 (" + result["error"] + ")。入力値・Gitのエラー本文は表示しません。"
    lines = ["保存状況（読み取りのみ・通信なし）"]
    targets = [("親Wiki", result["wiki"])]
    targets += [("案件 " + item.get("path", item["page"]), item["diagnostic"]) for item in result["projects"]]
    for name, report in targets:
        files, git = report.get("files", {}), report["git"]
        file_state = files.get("state", "not_checked")
        file_text = {"present": "あり", "partial_limit": "件数上限まで確認", "missing": "なし"}.get(
            file_state, "未確認 (" + file_state + ")")
        if "files" in files:
            file_text += f"・{files['files']}ファイル（リンク先未確認 {files['symlinks_not_followed']}件）"
        git_text = {"checked": "履歴あり", "unborn": "初回commit前", "not_initialized": "未初期化",
                    "not_independent": "親Gitの配下（独立Gitなし）"}.get(
                        git["state"], "未確認 (" + git["state"] + ")")
        kind = {"directory": "独立Git", "worktree": "Git worktree", "git_file": "Git管理先ファイル"}.get(
            git["kind"], "Git")
        lines.append(f"{name}: ファイル {file_text} / {kind}: {git_text}")
        if "head" in git:
            lines.append("  最新commit: " + (git["head"] or "なし（初回commit前）"))
            lines.append("  この範囲の履歴: " + (git["scope_last_commit"] or "なし"))
            c = git["changes"]
            lines.append(f"  追跡 {git['tracked_entries']}件 / 未commit: stage {c['staged']}・未stage {c['unstaged']}・競合 {c['conflicted']} / 未追跡 {c['untracked']}・ignored {c['ignored']}")
            u = git["upstream"]
            lines.append("  上流: " + (f"ローカルrefのみ（先行 {u['ahead']}・遅れ {u['behind']}）" if u["state"] == "local_ref_only" else "ローカル追跡refなし／解決不能"))
    lines += ["残り: 別媒体は未確認。既存の記録・本人申告を別途照合してください。復元は未確認です。",
              "ignored・未追跡は履歴保存済みではありません。件数はGitの項目数（ディレクトリを1件とする場合あり）。",
              "ローカルrefの一致は現在のリモート保存・バックアップ・復元の保証ではありません。submodule内部は未確認です。"]
    return "\n".join(lines)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes malicious input and may expose secrets.
        raise Unchecked("invalid_arguments")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = Parser(description="登録案件の保存状況を読み取りだけで確認する", allow_abbrev=False)
    parser.add_argument("--ws", required=True)
    parser.add_argument("--project")
    parser.add_argument("--json", action="store_true")
    code = 0
    try:
        args = parser.parse_args(argv)
        result = diagnose(args.ws, args.project)
    except Unchecked as exc:
        result, code = {"error": str(exc)}, 2
    except (OSError, ValueError, RuntimeError):
        result, code = {"error": "diagnostic_unavailable"}, 2
    print(json.dumps(result, ensure_ascii=False, indent=2) if "--json" in argv else render(result))
    return code


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

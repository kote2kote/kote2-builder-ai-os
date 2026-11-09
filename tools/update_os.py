#!/usr/bin/env python3
"""kote2 Builder AI OS の本体（OS のファイル）を新しい版にする。本人のもの（wiki/・projects/・recipes/ など）には触らない。

使い方（ワークスペースのいちばん上で。確認済みの旧版から起動し、未検証の新版は実行しない）:
  python3 -I tools/update_os.py check --from <検証済みの新しい版>      見るだけ（ファイルも git も変えない）
  python3 -I tools/update_os.py apply --from <検証済みの新しい版> --plan <番号> [--overwrite <ファイル> ...]
  python3 -I <git領域>/builder-os-update/recover.py recover --ws <ワークスペース>   保存した旧版で対象限定復旧
古い版からの初回導入は、この復旧機能の保証外。本人が別途確認した更新器を一度だけ使う（README参照）。
開発用（新しい版のフォルダで）:
  python3 tools/update_os.py manifest [--check]   OS のファイルの一覧 tools/os-files.txt を作り直す（--check は古ければ止まるだけ）

- 新しい版のフォルダ = 配られたひな形の中身（AGENTS.md と tools/os-files.txt があるフォルダ）。読むだけ。
- OS のファイルになれるのは、この道具の中で決めた場所だけ（OS_FILES と tools/ の中）。一覧に何が書かれていても、それ以外の場所は読まない・書かない。
- 消さない。新しい版で使わなくなった OS のファイルは、名前を知らせるだけ（消すかは本人と決める）。
- ワークスペースで書き換えられた OS のファイル（前の版の一覧と中身が違う）は、--overwrite で名前を指定したときだけ置き換える。前の中身は git の履歴に残る。
- .gitignore は、ワークスペースで足された行を残したまま新しい版の行を足す（--overwrite は要らない）。
- 書く先やその途中のフォルダがリンクなら、何も書かずに止まる。1回の更新を1つの commit にする。失敗したら書いたファイルを元に戻す。
- OS のファイルに commit されていない変更があれば止まる。ほかの場所の commit されていない変更には触らず、commit にも入れない。
- 本人の承認: apply は、書く前に本人の画面に確認の窓を出し（macOS・Windows）、本人が「更新する」を押したときだけ書く。
  AI がふだん使う道具（コマンドの実行・ファイルの読み書き）では窓のボタンを押せないので、この道具での更新は本人の操作なしには進まない
  （画面の操作を自動化する許可を AI に与えている環境では、この限りではない）。Windowsの窓が出せないときは停止し、端末入力へ自動で切り替えない。
  その他のOSでは本人が自分のターミナルで apply を実行し、「更新する」と打つ（AI も同じように打てるので、こちらは弱い）。
- 防げないこと: ワークスペースに書き込める AI が、この道具を使わずに OS のファイルを書き換えること。承認を強制するには権限を分ける必要があり、
  この道具はそこまではしない。道具を通った更新の commit には「確認の窓で承認」と入るが、これは承認の証拠ではなく目印（まねできる）。
- AI へ: 窓は省けない。本人が「確認はいらない」「そのまま入れて」と言ったときは、check の結果を伝えて同じ返事の中で apply してよい
  （窓が本人の確認になる）。この道具を使わずに OS のファイルを写したり書き換えたりしない（本人の承認のない更新になる。
  上のとおり、この道具では止められないので、守るのは AI の役目）。
- 戻し方: 完了した更新は `git revert <その commit>`。中断時は保存した旧版で復旧。追加編集・不明なlockは上書きせず停止する。
- commitは固定treeのcommit-treeと条件付きupdate-ref。pre-commitを実行し、commit-msg/prepare-commit-msg/post-commitと署名は実行しない。Gitのref/index hookは動き得る。
- 対応試験はmacOS。電源断・同権限の瞬間的な競合・ACL/xattr/所有者の保存・悪意あるhookは保証外。Release検証は別途必要。
- 終了コード: 0 = できた・変更なし / 2 = 使い方の誤り / 3 = ワークスペースや一覧の状態で止めた / 4 = 計画の番号が違う（check のあとに何か変わった）
  / 5 = 書き換えられたファイルがあり --overwrite が要る / 6 = 本人が承認しなかった（やめる・時間切れ・窓を出せない） / 7 = 中断・復旧停止
"""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MANIFEST = "tools/os-files.txt"
OS_FILES = {"VERSION", "AGENTS.md", "CLAUDE.md", "README.md", "DESIGN.md", ".gitignore", ".claude/settings.json", "wiki/README.md"}
STABLE_VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
LEGACY_VERSION = r"[0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]+"
NATIVE_FILES = frozenset(['.agents/skills/create-prototype/SKILL.md', '.agents/skills/create-prototype/references/builder-handoff.md', '.agents/skills/create-prototype/references/kinds.md', '.agents/skills/create-prototype/references/manual.html', '.agents/skills/create-prototype/scripts/shot.mjs', '.agents/skills/design-review/SKILL.md', '.agents/skills/design-review/scripts/shot.mjs', '.agents/skills/visualize-project-architecture/SKILL.md', '.agents/skills/visualize-project-architecture/agents/openai.yaml', '.agents/skills/visualize-project-architecture/references/diagram-strategy.md', '.agents/skills/visualize-project-architecture/references/visual-style.md', '.agents/skills/visualize-project-architecture/scripts/shot.mjs', '.claude/rules/builder-os-safety.md', '.claude/skills/create-prototype/SKILL.md', '.claude/skills/create-prototype/references/builder-handoff.md', '.claude/skills/create-prototype/references/kinds.md', '.claude/skills/create-prototype/references/manual.html', '.claude/skills/create-prototype/scripts/shot.mjs', '.claude/skills/design-review/SKILL.md', '.claude/skills/design-review/scripts/shot.mjs', '.claude/skills/explainer-video/SKILL.md', '.claude/skills/explainer-video/character/TERMS.md', '.claude/skills/explainer-video/character/cat1.png', '.claude/skills/explainer-video/character/cat2.png', '.claude/skills/explainer-video/character/cat3.png', '.claude/skills/explainer-video/character/cat4.png', '.claude/skills/explainer-video/character/cat5.png', '.claude/skills/explainer-video/character/cat6.png', '.claude/skills/explainer-video/character/cat7.png', '.claude/skills/explainer-video/character/cat8.png', '.claude/skills/explainer-video/character/character.js', '.claude/skills/explainer-video/engine/explainer.css', '.claude/skills/explainer-video/engine/explainer.js', '.claude/skills/explainer-video/engine/icons.js', '.claude/skills/explainer-video/engine/render-video.mjs', '.claude/skills/explainer-video/examples/mcp/evidence.md', '.claude/skills/explainer-video/examples/mcp/index.html', '.claude/skills/explainer-video/examples/mcp/plan.md', '.claude/skills/explainer-video/examples/mcp/scene.js', '.claude/skills/explainer-video/references/icon-catalog/index.html', '.claude/skills/explainer-video/references/icon-catalog/scene.js', '.claude/skills/explainer-video/references/scene-format.md', '.claude/skills/visualize-project-architecture/SKILL.md', '.claude/skills/visualize-project-architecture/agents/openai.yaml', '.claude/skills/visualize-project-architecture/references/diagram-strategy.md', '.claude/skills/visualize-project-architecture/references/visual-style.md', '.claude/skills/visualize-project-architecture/scripts/shot.mjs', '.codex/config.toml'])
OS_DIRS = ("tools/",)
SKIP_NAMES = {".DS_Store", "__pycache__", ".state"}
MERGE_LINES = {".gitignore"}  # 行の集まりなので、ワークスペースで足した行を残して足し合わせる
OSASCRIPT = "/usr/bin/osascript"  # 本人の画面に確認の窓を出す（macOS）
ASK_SECONDS = 110  # 窓を出しておく秒数（AI の道具の待ち時間の既定 2 分に収める）
JOURNAL = "builder-os-update"
RUNNER_BYTES = Path(__file__).read_bytes()
LOCK_FD = None
LOCK_PATH = None
WINDOWS = os.name == "nt"
WINDOWS_GIT_GUARD = """
import msvcrt, os, stat, subprocess, sys
from pathlib import Path
path = Path(sys.argv[1])
for current in (path, *path.parents):
    info = current.lstat()
    if stat.S_ISLNK(info.st_mode) or info.st_file_attributes & 0x400:
        raise RuntimeError('update lock is a reparse point')
before = path.lstat()
descriptor = os.open(path, os.O_RDWR | os.O_BINARY)
try:
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or not opened.st_ino or not os.path.samestat(before, opened) or not os.path.samestat(opened, path.lstat()):
        raise RuntimeError('update lock changed')
    os.lseek(descriptor, 1, os.SEEK_SET)
    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    try:
        result = subprocess.call(sys.argv[2:])
    finally:
        os.lseek(descriptor, 1, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
finally:
    os.close(descriptor)
sys.exit(result)
"""


class Stop(Exception):
    def __init__(self, msg, code=3):
        super().__init__(msg)
        self.code = code


def sha(data):
    return hashlib.sha256(data).hexdigest()


def is_os_path(rel):
    """OS のファイルになれる場所か（一覧の中身ではなく、ここで決める）。"""
    raw = rel.split("/")
    parts = Path(rel).parts
    if not rel or rel.startswith("/") or "\\" in rel or rel == MANIFEST or any(s in ("", ".", "..") for s in raw):
        return False
    if any(p == ".git" or p.startswith(".git/") for p in parts):
        return False
    if rel in OS_FILES or rel in NATIVE_FILES:
        return True
    return rel.startswith(OS_DIRS) and len(parts) >= 2 and not set(parts) & SKIP_NAMES


def read_manifest(root, past=None, raw=None):
    """{path: sha}, version。一覧が無ければ (None, None)。past に dict を渡すと、昔の正式な版のハッシュ（old の行）も集める。"""
    p = root / MANIFEST
    if raw is None and (not no_links(root, MANIFEST) or not p.is_file()):
        return None, None
    files, version = {}, None
    for line in (raw if raw is not None else p.read_bytes()).decode("utf-8").splitlines():
        if line.startswith("version:"):
            if version is not None:
                raise Stop("OS一覧の版が重複しています")
            version = line.split(":", 1)[1].strip()
        elif line.startswith("old "):
            h, _, rel = line[4:].partition("  ")
            if past is not None and rel:
                past.setdefault(rel.strip(), set()).add(h.strip())
        elif line.strip() and not line.startswith("#"):
            h, _, rel = line.partition("  ")
            if not rel or rel.strip() in files or len(h.strip()) != 64 or any(char not in "0123456789abcdef" for char in h.strip()):
                raise Stop(f"{p} の行の形が違います: {line[:80]}", 3)
            files[rel.strip()] = h.strip()
    if version is None or not re.fullmatch(rf"(?:{STABLE_VERSION}|{LEGACY_VERSION})", version):
        raise Stop("OS一覧の版の形式が不正です")
    if re.fullmatch(STABLE_VERSION, version) or "VERSION" in files or (root / "VERSION").exists() or is_link(root / "VERSION"):
        if "VERSION" not in files or product_version(root) != version:
            raise Stop("VERSIONとOS一覧の版が一致しません")
        if sha(state_bytes(file_state(root, "VERSION"))) != files["VERSION"]:
            raise Stop("VERSIONとOS一覧のhashが一致しません")
    return files, version


def product_version(root):
    state = file_state(root, "VERSION")
    if state is None or state["mode"] != 0o644:
        raise Stop("VERSION（mode 0644）が必要です")
    try:
        value = state_bytes(state).decode("ascii")
    except UnicodeError as error:
        raise Stop("VERSIONは安定版番号1行が必要です") from error
    if not re.fullmatch(STABLE_VERSION + r"\n?", value):
        raise Stop("VERSIONは安定版番号1行が必要です")
    return value.removesuffix("\n")


def past_versions(root, rel, current):
    """開発用: この repo の git の履歴にある rel の昔の版のハッシュ（いまの中身は除く）。"""
    prefix = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-prefix"], capture_output=True, text=True, encoding="utf-8")
    if prefix.returncode:
        return set()
    path = prefix.stdout.strip() + rel
    commits = subprocess.run(["git", "-C", str(root), "log", "--format=%H", "--", rel], capture_output=True, text=True, encoding="utf-8").stdout.split()
    out = set()
    for c in commits:
        r = subprocess.run(["git", "-C", str(root), "show", f"{c}:{path}"], capture_output=True)
        if r.returncode == 0:
            out.add(sha(r.stdout))
    return out - {current}


def make_manifest(root, version=None):
    canonical_version = product_version(root)
    if version is not None and version != canonical_version:
        raise Stop("--versionはVERSIONと一致する値だけ指定できます")
    version = canonical_version
    rels = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if no_links(root, rel) and p.is_file() and is_os_path(rel):
            rels.append(rel)
    out = ["# kote2 Builder AI OS の本体のファイル（tools/update_os.py が使う。手で直さない）", f"version: {version}"]
    cur = {r: sha((root / r).read_bytes()) for r in rels}
    out += [f"{cur[r]}  {r}" for r in rels]
    out += ["# 昔の正式な版（ワークスペースのファイルがこれと同じなら、書き換えられていないと分かる）"]
    out += [f"old {h}  {r}" for r in rels for h in sorted(past_versions(root, r, cur[r]))]
    return "\n".join(out) + "\n"


def no_links(root, rel):
    """root から rel までの途中のフォルダとファイルにリンクが無いか。"""
    cur = Path(root)
    if is_link(cur):
        return False
    if WINDOWS and any(is_link(parent) for parent in cur.absolute().parents):
        return False
    for part in Path(rel).parts:
        cur = cur / part
        if is_link(cur):
            return False
    return True


def is_link(path):
    try:
        info = Path(path).lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def safe_open(path, flags, mode=0o600):
    """既存の実体を読書き前に照合する。作成は排他的に行い、リンク・reparseは拒否する。"""
    path = Path(path)
    if flags & os.O_TRUNC or not no_links(path.parent, path.name):
        raise Stop("安全に開けないファイルです", 7)
    try:
        before = path.lstat()
    except FileNotFoundError:
        before = None
        if not flags & os.O_CREAT:
            raise
        flags |= os.O_EXCL
    if before is not None and (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1):
        raise Stop("通常ファイルではないかハードリンクです", 7)
    if not WINDOWS:
        flags |= os.O_NOFOLLOW
    else:
        flags |= os.O_BINARY
    descriptor = os.open(path, flags, mode)
    try:
        opened = os.fstat(descriptor)
        current = path.lstat()
        if (not no_links(path.parent, path.name) or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1 or not opened.st_ino or not os.path.samestat(opened, current)
                or before is not None and not os.path.samestat(before, opened)):
            raise Stop("開く間にファイルの実体が変わりました", 7)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def set_mode(descriptor, path, mode):
    if not WINDOWS:
        os.fchmod(descriptor, mode & 0o777)
        return
    if not no_links(Path(path).parent, Path(path).name) or not os.path.samestat(os.fstat(descriptor), Path(path).lstat()):
        raise Stop("権限設定先の実体が変わりました", 7)
    if mode not in (0o600, 0o644, 0o755) or not os.fstat(descriptor).st_mode & stat.S_IWRITE:
        raise Stop("Windowsで表現できないmodeまたは読取専用ファイルです", 7)


def put(dest, data, mode):
    """dest をまるごと置き換える（同じフォルダに新しく作った一時ファイルに書いてから入れ替える）。dest の中身をその場で書き換えないので、
    ほかの場所と中身を共有していても（ハードリンク）その場所は変わらない。一時ファイルは毎回ほかと重ならない名前で新しく作るので
    （mkstemp。既にあるファイルやリンクは開かない）、ワークスペースのほかのファイルには触らない。途中で止まっても書きかけが残らない。"""
    if not no_links(dest.parent, dest.name):
        raise Stop("置換先または親がリンクです", 7)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".update-os-tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            set_mode(f.fileno(), tmp, mode)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except BaseException:
        os.unlink(tmp)
        raise


def merge_lines(new_bytes, cur_bytes):
    """新しい版の行のあとに、ワークスペースにだけある行を足す。"""
    new_lines = new_bytes.decode("utf-8").splitlines()
    extra = [l for l in cur_bytes.decode("utf-8").splitlines() if l.strip() and l not in new_lines]
    if not extra:
        return new_bytes
    head = "# ワークスペースで足した行（OS の更新で残したもの）"
    body = new_lines + ([""] if new_lines and new_lines[-1].strip() else [])
    if head not in extra:
        body.append(head)
    return ("\n".join(body + extra) + "\n").encode("utf-8")


# Three small official baselines, not user state. They travel through the same journal.
DEFAULTS = "tools/native-defaults.json"
NATIVE_CONFIG = {"AGENTS.md", ".claude/settings.json", ".codex/config.toml"}


def native_defaults(package):
    state = package.get(DEFAULTS)
    if state is None:
        return {}
    try:
        value = json.loads(state_bytes(state))
        if not isinstance(value, dict) or set(value) - NATIVE_CONFIG or any(not isinstance(v, str) for v in value.values()):
            raise ValueError()
        return value
    except (ValueError, UnicodeError) as error:
        raise Stop("公式設定の比較用データが不正です") from error


def user_sections(text):
    marks = ("<!-- builder-os:begin -->", "<!-- builder-os:end -->",
             "<!-- builder-user:begin -->", "<!-- builder-user:end -->")
    if any(text.count(mark) != 1 for mark in marks):
        raise Stop("AGENTSの区画境界が不正です。手編集を保持して差分を確認してください")
    positions = [text.index(mark) for mark in marks]
    if positions != sorted(positions) or not text.startswith(marks[0]):
        raise Stop("AGENTSの区画順序が不正です")
    end = positions[1] + len(marks[1])
    return text[:end], text[end:]


def merge_native(rel, old, current, new):
    """Return None for legacy/unsupported input; conflicts never mean overwrite permission."""
    if old is None:
        return None
    try:
        current, new = current.decode("utf-8"), new.decode("utf-8")
        if rel == "AGENTS.md":
            base_os, _ = user_sections(old)
            cur_os, user = user_sections(current)
            new_os, _ = user_sections(new)
            if cur_os not in (base_os, new_os):
                raise Stop("AGENTSのOS区画に独自編集があります。保持して差分を解決してください")
            return (new_os + user).encode("utf-8")
        if rel == ".claude/settings.json":
            def unique(pairs):
                result = {}
                for key, val in pairs:
                    if key in result:
                        raise ValueError("duplicate JSON key")
                    result[key] = val
                return result
            base, cur, nxt = [json.loads(t, object_pairs_hook=unique) for t in (old, current, new)]
            # Validate known rule containers before merging. Invalid additions
            # can make the CLI discard the settings file, including its denies.
            for settings in (base, cur, nxt):
                if not isinstance(settings, dict):
                    raise Stop("Claude設定はobjectである必要があります")
                permissions = settings.get("permissions", {})
                sandbox = settings.get("sandbox", {})
                if not isinstance(permissions, dict) or not isinstance(sandbox, dict):
                    raise Stop("permissions/sandboxはobjectである必要があります")
                filesystem = sandbox.get("filesystem", {})
                if not isinstance(filesystem, dict):
                    raise Stop("sandbox.filesystemはobjectである必要があります")
                for container, fields, negation in (
                        (permissions, ("deny", "ask", "allow"), r"\s*(?:Read|Edit)\(\s*!"),
                        (filesystem, ("denyRead", "denyWrite"), r"\s*!")):
                    for field in fields:
                        rules = container.get(field, [])
                        if not isinstance(rules, list) or not all(isinstance(rule, str) for rule in rules):
                            raise Stop("権限規則は文字列の配列である必要があります: " + field)
                        if any(re.match(negation, rule) for rule in rules):
                            raise Stop("否定規則を含む権限配列は自動統合しません: " + rel)
            absent = object()
            def merge(a, b, c, path=()):
                # Safety values may only preserve the baseline or strengthen lists.
                safety = path[:1] in (("permissions",), ("sandbox",))
                if b == a or b == c:
                    return c
                if isinstance(a, dict) and isinstance(b, dict) and isinstance(c, dict):
                    out = {}
                    for key in sorted(a.keys() | b.keys() | c.keys()):
                        value = merge(a.get(key, absent), b.get(key, absent), c.get(key, absent), path + (key,))
                        if value is not absent:
                            out[key] = value
                    return out
                if path in (("permissions", "deny"), ("permissions", "ask"),
                             ("sandbox", "filesystem", "denyRead"), ("sandbox", "filesystem", "denyWrite")):
                    previous = [] if a is absent else a
                    incoming = [] if c is absent else c
                    if all(isinstance(v, list) for v in (previous, b, incoming)) and all(x in b for x in previous):
                        return incoming + [x for x in b if x not in previous and x not in incoming]
                if path == ("sandbox", "credentials", "envVars"):
                    previous = [] if a is absent else a
                    incoming = [] if c is absent else c
                    if all(isinstance(v, list) for v in (previous, b, incoming)) and all(x in b for x in previous):
                        if (all(isinstance(x, dict) and set(x) == {"name", "mode"} and isinstance(x["name"], str) and x["mode"] == "deny" for x in b)
                                and len({x["name"] for x in b}) == len(b)):
                            return incoming + [x for x in b if x not in previous and x not in incoming]
                if a == c and not safety:
                    return b
                raise Stop("利用者設定と標準設定が競合しています: " + rel + " / " + ".".join(path))
            return (json.dumps(merge(base, cur, nxt), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if rel == ".codex/config.toml":
            import tomllib
            base, cur, nxt = [tomllib.loads(t) for t in (old, current, new)]
            # Preserve comments/unknown tables byte-for-byte. Ambiguous edits stop.
            if not old or current.count(old) != 1:
                raise Stop("Codex設定の書式または標準部分に独自編集があります。差分を確認してください")
            result = current.replace(old, new, 1)
            parsed = tomllib.loads(result)
            for key in ("approval_policy", "default_permissions", "permissions", "web_search", "shell_environment_policy"):
                if parsed.get(key) != nxt.get(key):
                    raise Stop("Codex安全設定への追加・変更を自動統合しません: " + key)
            if any(key in parsed for key in ("sandbox_mode", "sandbox_workspace_write", "profiles")):
                raise Stop("Codex旧sandboxまたは別profileとの混在を解決してください")
            return result.encode("utf-8")
    except (ValueError, UnicodeError, ImportError) as error:
        raise Stop("設定を安全に統合できません。元の内容を保持して差分を確認してください: " + rel) from error
    return None


def git(ws, *args, env=None, input=None):
    # --no-optional-locks: git status が index を書き直さない（check は git の状態も変えない）
    binary = isinstance(input, bytes)
    command = ["git", "--literal-pathspecs", "--no-optional-locks", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-C", str(ws), *args]
    if WINDOWS and LOCK_FD is not None:
        if LOCK_PATH is None:
            raise Stop("更新ロックの場所を確認できません", 7)
        command = [sys.executable, "-I", "-c", WINDOWS_GIT_GUARD, str(LOCK_PATH), *command]
    process = subprocess.Popen(command,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE if input is not None else None, text=not binary,
                               env={**os.environ, **(env or {})}, start_new_session=True, encoding=None if binary else "utf-8",
                               pass_fds=(LOCK_FD,) if LOCK_FD is not None and not WINDOWS else ())
    try:
        output, error = process.communicate(input)
    except BaseException:
        process.communicate()
        raise
    if process.returncode:
        raise Stop(f"git {' '.join(args)} が失敗しました: {error.strip()}")
    return output.decode() if binary else output


def file_state(root, rel):
    if not no_links(root, rel):
        raise Stop(f"リンクが見つかりました: {rel}")
    path = root / rel
    if path.exists() and not path.is_file():
        raise Stop(f"通常ファイルではありません: {rel}")
    if not path.exists():
        return None
    descriptor = safe_open(path, os.O_RDONLY)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise Stop(f"通常ファイルではないかハードリンクです: {rel}")
        data = stream.read()
        after = os.fstat(stream.fileno())
        if any(getattr(before, name) != getattr(after, name) for name in ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")):
            raise Stop(f"読む間に変わりました: {rel}")
    mode = (0o644 if before.st_mode & stat.S_IWRITE else 0o444) if WINDOWS else stat.S_IMODE(before.st_mode)
    return {"data": base64.b64encode(data).decode("ascii"), "mode": mode}


def state_bytes(state):
    return base64.b64decode(state["data"], validate=True)


def fingerprint(value):
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def index_states(ws, paths):
    entries = {path: None for path in paths}
    for line in git(ws, "ls-files", "--stage", "-z", "--", *paths).split("\0"):
        if line:
            metadata, name = line.split("\t", 1)
            mode, digest, stage = metadata.split()
            if stage != "0":
                raise Stop(f"index が競合しています: {name}")
            entries[name] = [mode, digest]
    return entries


def journal_path(ws):
    return Path(git(ws, "rev-parse", "--absolute-git-dir").strip()) / JOURNAL


def check_git_locks(ws, head_ref):
    for name in {"index", "HEAD", "packed-refs", head_ref}:
        resolved = Path(git(ws, "rev-parse", "--git-path", name).strip())
        if not resolved.is_absolute():
            resolved = ws / resolved
        lock = Path(str(resolved) + ".lock")
        if lock.exists() or is_link(lock):
            raise Stop(f"gitのlockが残っています。所有者を確かめずには削除しません: {lock.name}", 7)


def pending(ws):
    output_state = "tools/.state/output-migration"
    for name in (output_state + "/transaction.json", output_state + "/apply.lock"):
        target = ws / name
        if os.path.lexists(target):
            if not no_links(ws, name) or not target.is_file() or target.stat().st_nlink != 1:
                raise Stop("output一括移行の記録を確認できません。OS更新より先に移行の状態を確認してください", 7)
            if name.endswith("apply.lock"):
                raise Stop("output一括移行のlockがあります。先にoutput_migration.py resumeで確認してください", 7)
            try:
                if target.stat().st_size > 16 * 1024 * 1024:
                    raise ValueError("large journal")
                record = json.loads(target.read_bytes())
                if not isinstance(record, dict) or record.get("phase") != "complete":
                    raise ValueError("unfinished journal")
                expected = hashlib.sha256(json.dumps({key: value for key, value in record.items() if key != "journal_hash"},
                    ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                if record.get("journal_hash") != expected:
                    raise ValueError("invalid journal")
            except (OSError, ValueError, TypeError):
                raise Stop("output一括移行が中断中か記録不明です。OS更新より先にoutput_migration.py resumeで確認してください", 7)
    path = journal_path(ws)
    if path.exists() or is_link(path):
        raise Stop(f"OS更新が中断しています。途中の状態をcommitしないでください。復旧: python3 -I '{path / 'recover.py'}' recover --ws '{ws}'", 7)


def all_reasons(items):
    return f"全{len(items)}件（以下に全件表示）:\n" + "\n".join("- " + item for item in items)


def version_order(value):
    """release_package.version_order と同じ順序。日付形式の旧版は安定版より前。"""
    return (1 if re.fullmatch(STABLE_VERSION, value) else 0, *map(int, re.split(r"[-.]", value)))


def plan(ws, new):
    pending(ws)
    check_git_locks(ws, git(ws, "rev-parse", "--symbolic-full-name", "HEAD").strip())
    past = {}
    source_manifest = file_state(new, MANIFEST)
    if source_manifest and source_manifest["mode"] not in (0o644, 0o755):
        raise Stop("配布manifestのmodeは0644か0755にしてください")
    new_files, new_ver = read_manifest(new, past, state_bytes(source_manifest) if source_manifest else None)
    _, installed_ver = read_manifest(ws)
    if installed_ver and new_ver and version_order(new_ver) < version_order(installed_ver):
        raise Stop(f"新しい版のフォルダ（{new_ver}）は、入っている版（{installed_ver}）より古い版です。古い版へは戻しません。何も変更していません", 2)
    if new_files is None or not (new / "AGENTS.md").is_file():
        raise Stop(f"{new} は新しい版のフォルダではありません（AGENTS.md と {MANIFEST} がありません）", 2)
    bad = [r for r in new_files if not is_os_path(r)]
    if bad:
        raise Stop("新しい版の一覧に、OS のファイルになれない場所が入っています。何も書かずに止めました。範囲外 " + all_reasons(bad), 3)
    package = {MANIFEST: source_manifest}
    for rel, h in new_files.items():
        package[rel] = file_state(new, rel)
        if package[rel] is None or sha(state_bytes(package[rel])) != h:
            raise Stop(f"新しい版のフォルダの {rel} が一覧と合いません（配られたものが壊れているか、途中です）", 3)
        if package[rel]["mode"] not in (0o644, 0o755):
            raise Stop(f"配布ファイルのmodeは0644か0755にしてください: {rel}")
    links = [r for r in list(new_files) + [MANIFEST] if not no_links(ws, r)]
    if links:
        raise Stop("ワークスペースの書く先（またはその途中のフォルダ）がリンクです。何も書かずに止めました: " + "、".join(links), 3)
    shared = [r for r in list(new_files) + [MANIFEST] if (ws / r).is_file() and (ws / r).stat().st_nlink > 1]
    if shared:
        raise Stop("ワークスペースの書く先が、ほかの場所と中身を共有しています（ハードリンク）。何も書かずに止めました: " + "、".join(shared), 3)
    dirty = git(ws, "status", "--porcelain", "--ignored", "--untracked-files=all", "--", *new_files, MANIFEST).splitlines()
    if dirty:
        raise Stop("OS のファイルに commit されていない変更（または git に入っていないファイル）があります。"
                   "先に記録して commit するか、元に戻してから、もう一度実行してください。" + all_reasons([line[3:] for line in dirty]), 3)
    flagged = git(ws, "ls-files", "-v", "-z", "--", *package).split("\0")
    if any(entry and not entry.startswith("H ") for entry in flagged):
        raise Stop("OS対象のindexにskip-worktree等の特別な設定があります。解除してから確認してください")
    before = {rel: file_state(ws, rel) for rel in package}
    if any(state and state["mode"] not in (0o644, 0o755) for state in before.values()):
        raise Stop("OS対象のmodeが0644/0755以外です。Gitで取消できない権限変更を避けるため停止します。本人が権限を確認してください")
    current_index = index_states(ws, list(package))
    git_modes = {rel: "100755" if state["mode"] & 0o111 else "100644" for rel, state in package.items()}
    if WINDOWS:
        inventory_state = file_state(new, "release-files.json")
        if inventory_state is None:
            raise Stop("Windowsではmodeを保持した正式配布一覧 release-files.json が必要です")
        inventory = json.loads(state_bytes(inventory_state))
        if not isinstance(inventory, dict) or inventory.get("format") != 1 or not isinstance(inventory.get("files"), dict):
            raise Stop("正式配布一覧の形式が不正です")
        for rel, state in package.items():
            entry = inventory["files"].get(rel)
            if (not isinstance(entry, dict) or entry.get("sha256") != sha(state_bytes(state))
                    or type(entry.get("mode")) is not int or entry["mode"] not in (0o644, 0o755)):
                raise Stop(f"正式配布一覧のhash/modeが一致しません: {rel}")
            git_modes[rel] = "100755" if entry["mode"] == 0o755 else "100644"
    old_files, old_ver = read_manifest(ws)
    ignored = sorted(r for r in (old_files or {}) if not is_os_path(r))
    old_files = {r: h for r, h in (old_files or {}).items() if is_os_path(r)} if old_files is not None else None
    old_defaults = {}
    if (old_files or {}).get(DEFAULTS):
        old_default_state = file_state(ws, DEFAULTS)
        if old_default_state is None or sha(state_bytes(old_default_state)) != old_files[DEFAULTS]:
            raise Stop("旧公式設定の比較用データが変更されています。何も書かずに停止しました")
        old_defaults = native_defaults({DEFAULTS: old_default_state})
    new_defaults = native_defaults(package)
    for rel, value in new_defaults.items():
        if rel not in package or value.encode("utf-8") != state_bytes(package[rel]):
            raise Stop("新公式設定と比較用データが一致しません: " + rel)
    steps = []  # (rel, 何をするか, 書き換えられているか)
    merged = {}  # rel → 書く中身（足し合わせたファイル）
    native_conflicts = []
    for rel in sorted(new_files):
        cur = ws / rel
        if cur.exists() and not cur.is_file():
            raise Stop(f"ワークスペースの {rel} がファイルではありません。何も書かずに止めました", 3)
        if not cur.exists():
            steps.append((rel, "足す", False))
            continue
        h = sha(state_bytes(before[rel]))
        if before[rel] == package[rel] and (not WINDOWS or current_index[rel] is not None and current_index[rel][0] == git_modes[rel]):
            continue
        base = (old_files or {}).get(rel)
        known = h == base or h in past.get(rel, set())  # 前の版の一覧か、昔の正式な版と同じ = 書き換えられていない
        if rel in NATIVE_CONFIG and not known and rel in old_defaults and rel in new_defaults:
            data = merge_native(rel, old_defaults[rel], state_bytes(before[rel]), state_bytes(package[rel]))
            if data is not None:
                if data == state_bytes(before[rel]) and before[rel]["mode"] == package[rel]["mode"]:
                    continue
                merged[rel] = data
                steps.append((rel, "標準を更新（利用者の設定を保持）", False))
                continue
        if rel in NATIVE_FILES and not known:
            native_conflicts.append(rel)
            continue
        if rel in MERGE_LINES and not known:
            data = merge_lines(state_bytes(package[rel]), state_bytes(before[rel]))
            if (data == state_bytes(before[rel]) and before[rel]["mode"] == package[rel]["mode"]
                    and (not WINDOWS or current_index[rel] is not None and current_index[rel][0] == git_modes[rel])):
                continue
            merged[rel] = data
            steps.append((rel, "新しい版の行を足す（ワークスペースで足した行は残す）", False))
            continue
        steps.append((rel, "新しくする", not known))
    if native_conflicts:
        raise Stop("公式配置に同名の独自ファイルがあります。上書きせず配置を確認してください。" + all_reasons(native_conflicts))
    unused = sorted(r for r in (old_files or {}) if r not in new_files and (ws / r).is_file())
    if (not steps and before[MANIFEST] == package[MANIFEST]
            and (not WINDOWS or current_index[MANIFEST] is not None and current_index[MANIFEST][0] == git_modes[MANIFEST])):
        steps = None  # 何も変わらない
    head = git(ws, "rev-parse", "HEAD").strip()
    expected = {rel: dict(package[rel]) for rel, _, _ in steps or []}
    expected[MANIFEST] = package[MANIFEST]
    for rel, data in merged.items():
        expected[rel]["data"] = base64.b64encode(data).decode("ascii")
    head_ref = git(ws, "rev-parse", "--symbolic-full-name", "HEAD").strip()
    key = {"head": head, "head_ref": head_ref, "package": package, "before": before, "expected": expected,
           "index": index_states(ws, list(package)), "steps": steps, "old_ver": old_ver, "new_ver": new_ver}
    if WINDOWS:
        key["git_modes"] = git_modes
    others = len(git(ws, "status", "--porcelain").splitlines())
    retained_settings = []
    if before.get(".claude/settings.json"):
        try:
            values = json.loads(state_bytes(before[".claude/settings.json"]))
            standard = json.loads(new_defaults.get(".claude/settings.json", "{}"))
            retained_settings += ["Claude: " + key for key in sorted(set(values) - set(standard))]
        except (ValueError, TypeError):
            retained_settings.append("Claude: 追加設定を解析できないため未点検")
    if before.get(".codex/config.toml"):
        try:
            import tomllib
            values = tomllib.loads(state_bytes(before[".codex/config.toml"]).decode("utf-8"))
            standard = tomllib.loads(new_defaults.get(".codex/config.toml", ""))
            retained_settings += ["Codex: " + key for key in sorted(set(values) - set(standard))]
        except (ValueError, ImportError, UnicodeError):
            retained_settings.append("Codex: 追加設定を解析できないため未点検")
    info = {"retained_settings": retained_settings, "old_ver": old_ver, "new_ver": new_ver, "no_base": old_files is None, "unused": unused, "ignored": ignored, "others": others,
            "head": head, "head_ref": head_ref, "before": before, "expected": expected, "package": fingerprint(package), "index": key["index"], "plan": fingerprint(key)[:12]}
    if WINDOWS:
        info["git_modes"] = git_modes
    return steps, info["plan"], merged, info


def check_ws(ws):
    if not (ws / "AGENTS.md").is_file() or not (ws / "wiki").is_dir():
        raise Stop(f"{ws} はワークスペースではありません（ワークスペースのいちばん上で実行してください）", 2)
    if subprocess.run(["git", "-C", str(ws), "rev-parse", "--is-inside-work-tree"], capture_output=True).returncode:
        raise Stop("ワークスペースが git の repo ではありません。先に git init して最初の commit をしてください", 3)
    if Path(git(ws, "rev-parse", "--show-toplevel").strip()).resolve() != ws.resolve():
        raise Stop("ワークスペースのいちばん上で実行してください", 2)


def show(steps, pid, info):
    print(f"OS の更新: {info['old_ver'] or '（版の記録なし）'} → {info['new_ver']}")
    if steps is None:
        print("変わるファイルはありません（もう新しい版です）")
    else:
        if not steps:
            print(f"- 新しくする: {MANIFEST}（OS のファイルの一覧だけ。ほかのファイルはもう新しい版と同じ）")
        for rel, act, changed in steps:
            mark = "  ※ワークスペースで書き換えられている（--overwrite が要る）" if changed else ""
            print(f"- {act}: {rel}{mark}")
    if info.get("retained_settings"):
        print("保持・未点検（権限の安全認定ではありません）: " + "、".join(info["retained_settings"]))
    if info["unused"]:
        print("新しい版では使わない OS のファイル（消していない。消すかは本人と決める）: " + "、".join(info["unused"]))
    if info["ignored"]:
        print("ワークスペースの一覧に OS のファイルになれない場所があったので、無視した（触っていない）。" + all_reasons(info["ignored"]))
    if steps is None:
        return
    if info["no_base"]:
        print("（このワークスペースには前の版の一覧がないので、昔の正式な版のどれとも違うファイルを「書き換えられている」として扱います。"
              "違いは `diff <ワークスペースのファイル> <新しい版のファイル>` で見られます）")
    print("変えないもの: wiki/（README.md を除く）・projects/・recipes/・imports/ と、上に無いファイル")
    if info["others"]:
        print(f"commit されていない変更が {info['others']} 件あります（OS の更新では触らず、commit にも入れません）")
    print("ここで止まってください。上の内容を本人に伝えて、この返事を終えてください。"
          "本人の「OS を新しくして」はこの確認を見る前の依頼なので、まだ OK ではありません。"
          "本人の次の返事で OK をもらってから apply してください。書き足しを profile などへ移すのも、その OK のあとです。"
          "（本人が先に「確認はいらない」「そのまま入れて」と言っていたときだけは、上の内容を伝えたあと、同じ返事の中で apply してかまいません）")
    print(f"apply は書く前に本人の画面に確認の窓を出し、本人が「更新する」を押したときだけ書きます（約 {round(ASK_SECONDS / 60)} 分で閉じます）。"
          "apply の前に、窓が出ることを本人に伝えてください。窓は省けません。本人が「確認はいらない」と言っても、"
          "この道具を使わずに OS のファイルを写したり書き換えたりしないでください（本人の承認のない更新になります）")
    print(f"plan {pid}")


WINDOWS_APPROVAL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$form = $null
$timer = $null
$script:decision = 'no'
try {
    if (-not [Environment]::UserInteractive) { throw 'No interactive desktop' }
    $payload = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([Console]::In.ReadToEnd())) | ConvertFrom-Json
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [System.Windows.Forms.Application]::EnableVisualStyles()
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'kote2 Builder AI OS - 更新の確認'
    $form.StartPosition = 'CenterScreen'
    $form.AutoScaleMode = 'Font'
    $form.Font = [System.Drawing.SystemFonts]::MessageBoxFont
    $form.TopMost = $true
    $form.MinimizeBox = $false
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $width = [Math]::Min(760, [Math]::Max(280, $screen.Width - 48))
    $height = [Math]::Min(600, [Math]::Max(240, $screen.Height - 80))
    $form.Size = New-Object System.Drawing.Size($width, $height)
    $form.MinimumSize = New-Object System.Drawing.Size([Math]::Min(360, $width), [Math]::Min(300, $height))
    $form.BackColor = [System.Drawing.ColorTranslator]::FromHtml('#f0efe2')
    $form.ForeColor = [System.Drawing.ColorTranslator]::FromHtml('#2f3a1c')
    $layout = New-Object System.Windows.Forms.TableLayoutPanel
    $layout.Dock = 'Fill'
    $layout.Padding = New-Object System.Windows.Forms.Padding(16)
    $layout.ColumnCount = 1
    $layout.RowCount = 2
    [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100)))
    [void]$layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    $details = New-Object System.Windows.Forms.RichTextBox
    $details.Dock = 'Fill'
    $details.ReadOnly = $true
    $details.DetectUrls = $false
    $details.WordWrap = $true
    $details.ScrollBars = 'Vertical'
    $details.BackColor = [System.Drawing.Color]::White
    $details.ForeColor = $form.ForeColor
    $details.Text = [string]$payload.message
    $buttons = New-Object System.Windows.Forms.FlowLayoutPanel
    $buttons.Dock = 'Fill'
    $buttons.AutoSize = $true
    $buttons.FlowDirection = 'RightToLeft'
    $buttons.WrapContents = $true
    $buttons.Padding = New-Object System.Windows.Forms.Padding(0, 12, 0, 0)
    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = 'やめる'
    $cancel.AutoSize = $true
    $cancel.MinimumSize = New-Object System.Drawing.Size(112, 36)
    $cancel.Add_Click({ $script:decision = 'no'; $form.Close() })
    $approve = New-Object System.Windows.Forms.Button
    $approve.Text = '更新する'
    $approve.AutoSize = $true
    $approve.MinimumSize = New-Object System.Drawing.Size(112, 36)
    $approve.Add_Click({ $script:decision = 'yes'; $form.Close() })
    $buttons.Controls.Add($cancel)
    $buttons.Controls.Add($approve)
    $layout.Controls.Add($details, 0, 0)
    $layout.Controls.Add($buttons, 0, 1)
    $form.Controls.Add($layout)
    $form.AcceptButton = $cancel
    $form.CancelButton = $cancel
    $form.Add_Shown({ $form.Activate(); [void]$cancel.Focus() })
    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = [int]$payload.seconds * 1000
    $timer.Add_Tick({ $script:decision = 'timeout'; $timer.Stop(); $form.Close() })
    $timer.Start()
    [void]$form.ShowDialog()
    [Console]::Out.Write($script:decision)
} catch {
    [Console]::Out.Write('unavailable')
    exit 1
} finally {
    if ($null -ne $timer) { $timer.Dispose() }
    if ($null -ne $form) { $form.Dispose() }
}
"""


def windows_powershell():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_directory = kernel.GetSystemDirectoryW
    get_directory.argtypes = (wintypes.LPWSTR, wintypes.UINT)
    get_directory.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    length = get_directory(buffer, len(buffer))
    if not length or length >= len(buffer):
        raise OSError("Windowsのシステムフォルダを確認できません")
    executable = Path(buffer.value) / "WindowsPowerShell/v1.0/powershell.exe"
    if not executable.is_file():
        raise OSError("Windows標準のPowerShellが見つかりません")
    return str(executable)


def cleanup_confirmation_folder(folder):
    """確認窓専用の一時フォルダだけを片付ける。リンクがあれば削除せず、失敗しても本人の答えは変えない。"""
    attempts = 6 if WINDOWS else 1  # Windowsでは終了直後のPowerShell/ウイルス検査が一瞬ファイルを掴むことがある
    for attempt in range(attempts):
        try:
            if is_link(folder) or any(is_link(entry) for entry in Path(folder).rglob("*")):
                print("警告: 確認窓の一時フォルダにリンクを検出したため削除しません。本人が確認してください: " + Path(folder).name,
                      file=sys.stderr)
            elif Path(folder).is_dir():
                shutil.rmtree(folder)
            return
        except OSError:
            if attempt + 1 < attempts:
                time.sleep(0.5)
    print("警告: 確認窓の一時フォルダを片付けられませんでした。使用中のプロセスを確認してから本人が片付けてください: "
          + Path(folder).name, file=sys.stderr)


def ask_windows(message, ws=None):
    payload = base64.b64encode(json.dumps(
        {"message": message, "seconds": ASK_SECONDS}, ensure_ascii=False
    ).encode("utf-8"))
    script = base64.b64encode(WINDOWS_APPROVAL_SCRIPT.encode("utf-16le")).decode("ascii")
    # PowerShellはプロファイルの場所を決められないとModuleAnalysisCache等を作業フォルダへ相対で書く。
    # 毎回新しい専用一時フォルダを作業フォルダ兼キャッシュ先にし、ワークスペースにもシステムフォルダにも書かせない。
    try:
        base = Path(tempfile.gettempdir()).resolve()
        if ws is not None and base.is_relative_to(Path(ws).resolve()):
            return "unavailable: 確認窓の一時フォルダがワークスペース内です"
        folder = Path(tempfile.mkdtemp(prefix="builder-os-confirm-", dir=base)).resolve()
    except OSError:
        return "unavailable: 確認窓の一時フォルダを作れません"
    try:
        if ws is not None and folder.is_relative_to(Path(ws).resolve()):
            return "unavailable: 確認窓の一時フォルダがワークスペース内です"
        # Windowsの環境変数名は大文字小文字を区別しないため、既存の同名変数を除いてから設定する
        environment = {key: value for key, value in os.environ.items() if key.upper() != "PSMODULEANALYSISCACHEPATH"}
        environment["PSModuleAnalysisCachePath"] = str(folder / "ModuleAnalysisCache")
        try:
            result = subprocess.run(
                [windows_powershell(), "-NoLogo", "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", script],
                input=payload, capture_output=True, timeout=ASK_SECONDS + 15, cwd=str(folder), env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            return "timeout"
        except (OSError, AttributeError):
            return "unavailable: Windowsの確認窓を起動できません"
        if result.returncode == 0 and result.stdout in (b"yes", b"no", b"timeout"):
            return result.stdout.decode("ascii")
        return "unavailable: Windowsの確認窓を表示・確認できません"
    finally:
        cleanup_confirmation_folder(folder)


def ask_human(steps, info, ws=None):
    """本人に聞く。本人が「更新する」を選んだときだけ "yes"。ほかは "no"（やめる）/ "timeout" / "unavailable: 理由"。"""
    changed = [r for r, _, c in steps if c]
    msg = (f"kote2 Builder AI OS を新しい版（{info['new_ver']}）にします。\n"
           f"変わるのは OS のファイル {len(steps)} 個と、その一覧だけです。あなたの記録・作ったもの・レシピは変わりません。")
    if "recovery" in info:
        msg = info["recovery"] + f"\n対象は OS 管理ファイル {len(info['expected'])} 個です。本人の追加編集を見つけた場合は停止します。"
    if changed:
        msg += "\n\nワークスペースで書き換えられていたファイルも置き換えます（前の中身は履歴に残ります）: " + "、".join(changed)
    if info.get("retained_settings"):
        msg += "\n\n保持・未点検の追加設定: " + "、".join(info["retained_settings"])
    if "approval" in info:
        msg += f"\n\nplan {info['plan']} / 承認 {info['approval']}\nパッケージ SHA-256: {info['package']}"
        msg += "\n対象とmode: " + "、".join(f"{rel} ({state['mode']:04o})" for rel, state in info["expected"].items())
    msg += "\n\nAI の説明を読んで、よければ「更新する」を押してください。あとで元に戻せます。"
    if WINDOWS:
        return ask_windows(msg, ws)
    if Path(OSASCRIPT).is_file():
        script = ["on run argv", "activate",
                  'display dialog (item 1 of argv) with title "kote2 Builder AI OS の更新" buttons {"やめる", "更新する"} '
                  'default button "やめる" cancel button "やめる" with icon caution giving up after ((item 2 of argv) as integer)',
                  "end run"]
        try:
            r = subprocess.run([OSASCRIPT, *sum((["-e", s] for s in script), []), msg, str(ASK_SECONDS)],
                               capture_output=True, text=True, timeout=ASK_SECONDS + 30)
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"unavailable: {e}"
        if r.returncode == 0 and "gave up:true" in r.stdout:
            return "timeout"
        if r.returncode == 0 and "button returned:更新する" in r.stdout:
            return "yes"
        if "-128" in r.stderr:
            return "no"
        return f"unavailable: {(r.stderr or r.stdout).strip()[:200]}"
    if sys.stdin.isatty() and sys.stdout.isatty():  # macOS 以外: 本人が自分のターミナルで実行したとき
        print(msg)
        try:
            return "yes" if input("更新するなら「更新する」と入力してください: ").strip() == "更新する" else "no"
        except EOFError:
            return "no"
    return "unavailable: 確認の窓を出せる環境ではありません"


@contextmanager
def update_lock(ws):
    global LOCK_FD, LOCK_PATH
    lock = journal_path(ws).with_suffix(".lock")
    descriptor = safe_open(lock, os.O_CREAT | os.O_RDWR)
    locked = False
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode) or os.fstat(descriptor).st_nlink != 1:
            raise Stop("更新ロックが通常ファイルではありません", 7)
        try:
            if WINDOWS:
                import msvcrt
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                os.lseek(descriptor, 1, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as error:
            raise Stop("ほかの更新・復旧が実行中か、排他を確保できません。実行状態と権限を確認してください", 7) from error
        LOCK_FD = descriptor
        LOCK_PATH = lock
        yield
    finally:
        LOCK_FD = None
        LOCK_PATH = None
        try:
            if WINDOWS and locked:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(descriptor)


def save_record(path, record):
    data = {"record": record, "sha256": fingerprint(record)}
    descriptor = safe_open(path / "state.next", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(json.dumps(data, sort_keys=True).encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(path / "state.next", path / "state.json")


def load_record(ws):
    path = journal_path(ws)
    if not no_links(path.parent, path.name) or not path.is_dir():
        raise Stop("復旧記録の場所が正しくありません。自動では触りません", 7)
    try:
        saved = json.loads(state_bytes(file_state(path, "state.json")))
        record = saved["record"]
        if saved["sha256"] != fingerprint(record) or record["format"] != 1 or record["workspace"] != str(ws):
            raise ValueError("記録の形式・ハッシュ・ワークスペースが一致しません")
        if any(not isinstance(record[key], str) or len(record[key]) != length or any(character not in "0123456789abcdef" for character in record[key])
               for key, length in (("approval", 64), ("head", len(git(ws, "rev-parse", "HEAD").strip())))):
            raise ValueError("承認またはHEADの形式が不正です")
        paths = set(record["expected"])
        if not paths or paths != set(record["before"]) or paths != set(record["index"]) or paths != set(record["expected_index"]):
            raise ValueError("対象集合が一致しません")
        if any(rel != MANIFEST and not is_os_path(rel) for rel in paths):
            raise ValueError("OS対象外のパスです")
        for states in (record["before"], record["expected"]):
            for state in states.values():
                if state is not None and (not isinstance(state["mode"], int) or not 0 <= state["mode"] <= 0o777 or not isinstance(state_bytes(state), bytes)):
                    raise ValueError("ファイル状態が不正です")
        if any(state is None or state["mode"] not in (0o644, 0o755) for state in record["expected"].values()):
            raise ValueError("適用するmodeが不正です")
        allowed_directories = {parent.as_posix() for rel in paths for parent in Path(rel).parents if parent != Path(".")}
        if not set(record["directories"]) <= allowed_directories:
            raise ValueError("生成ディレクトリが不正です")
        if sha(state_bytes(file_state(path, "recover.py"))) != record["runner"]:
            raise ValueError("旧版復旧処理のハッシュが一致しません")
        return record
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise Stop(f"復旧記録が壊れているか準備途中です。自動では触りません: {error}", 7)


def verify_recovery(ws, record):
    paths = list(record["expected"])
    staging = {stage_name(rel, state): state for states in (record["before"], record["expected"])
               for rel, state in states.items() if state is not None}
    for entry in journal_path(ws).iterdir():
        if entry.name in staging:
            current = file_state(journal_path(ws), entry.name)
            intended = staging[entry.name]
            if current is None or current["mode"] not in (0o600, intended["mode"]) or not state_bytes(intended).startswith(state_bytes(current)):
                raise Stop("更新用一時ファイルに追加編集があります。何も戻しません", 7)
        elif entry.name not in {"state.json", "state.next", "recover.py", "index", "index.lock", "COMMIT_EDITMSG"}:
            raise Stop(f"復旧記録に未知のファイル・ロックがあります。削除しません: {entry.name}", 7)
        else:
            file_state(journal_path(ws), entry.name)
    head = git(ws, "rev-parse", "HEAD").strip()
    if git(ws, "rev-parse", "--symbolic-full-name", "HEAD").strip() != record["head_ref"]:
        raise Stop("作業中のブランチが変わっています。自動復旧しません", 7)
    committed = head != record["head"]
    if committed:
        parents = git(ws, "rev-list", "--parents", "-n", "1", "HEAD").split()
        changed = set(filter(None, git(ws, "diff", "--name-only", "-z", record["head"], "HEAD").split("\0")))
        if head != record.get("commit") or parents[1:] != [record["head"]] or changed - set(paths) or f"Builder-OS-Plan: {record['plan']}" not in git(ws, "log", "-1", "--format=%B"):
            raise Stop("HEADが別の作業で変わっています。履歴と本人編集を保護するため復旧を停止します", 7)
        tree = {}
        for line in git(ws, "ls-tree", "-z", "HEAD", "--", *paths).split("\0"):
            if line:
                metadata, name = line.split("\t", 1)
                mode, kind, digest = metadata.split()
                tree[name] = [mode, digest]
        if tree != record["expected_index"]:
            raise Stop("commitの内容が承認内容と一致しません。自動復旧しません", 7)
    current_index = index_states(ws, paths)
    if any(entry and not entry.startswith("H ") for entry in git(ws, "ls-files", "-v", "-z", "--", *paths).split("\0")):
        raise Stop("対象indexの特別な設定が変わっています。自動復旧しません", 7)
    for rel in paths:
        allowed_index = [record["index"][rel], record["expected_index"][rel]] if committed else [record["index"][rel]]
        if current_index[rel] not in allowed_index:
            raise Stop(f"対象のindexに追加編集があります。何も戻しません: {rel}", 7)
        current = file_state(ws, rel)
        allowed = [record["expected"][rel]] if committed else [record["before"][rel], record["expected"][rel]]
        if current not in allowed:
            raise Stop(f"対象に追加編集・削除・mode変更があります。何も戻しません: {rel}", 7)
    check_git_locks(ws, record["head_ref"])
    return committed


def stage_name(rel, state):
    return "stage-" + fingerprint([rel, state])


def verify_applied(ws, record):
    verify_recovery(ws, record)
    if any(file_state(ws, rel) != state for rel, state in record["expected"].items()):
        raise Stop("書込後の対象が承認内容と一致しません。commitしません", 7)


def replace_state(ws, path, rel, state):
    if state is None:
        (ws / rel).unlink()
    else:
        staged = path / stage_name(rel, state)
        if staged.exists() or is_link(staged):
            current = file_state(path, staged.name)
            if current is None or current["mode"] not in (0o600, state["mode"]) or not state_bytes(state).startswith(state_bytes(current)):
                raise Stop("復旧用一時ファイルが記録と異なります。削除せず停止します", 7)
            staged.unlink()
        descriptor = safe_open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(state_bytes(state))
            set_mode(stream.fileno(), staged, state["mode"])
            stream.flush()
            os.fsync(stream.fileno())
        if os.stat(staged).st_dev != os.stat((ws / rel).parent).st_dev:
            raise Stop("git領域と対象が別ファイルシステムです。安全な置換を実行できません", 7)
        os.replace(staged, ws / rel)


def finish_transaction(ws, record):
    path = journal_path(ws)
    committed = verify_recovery(ws, record)
    if committed:
        git(ws, "reset", "-q", "HEAD", "--", *record["expected"])
    else:
        for rel, before in record["before"].items():
            verify_recovery(ws, record)
            if file_state(ws, rel) != before:
                replace_state(ws, path, rel, before)
        for rel in sorted(record["directories"], key=lambda value: len(Path(value).parts), reverse=True):
            directory = ws / rel
            if not no_links(ws, rel):
                raise Stop(f"生成ディレクトリがリンクです。触りません: {rel}", 7)
            if directory.is_dir():
                try:
                    directory.rmdir()
                except OSError:
                    pass
    finished = path.with_name(JOURNAL + "-finished-" + record["approval"])
    if finished.exists() or is_link(finished):
        raise Stop("完了記録の退避先が既にあります。自動削除しません", 7)
    os.rename(path, finished)
    try:
        shutil.rmtree(finished)
    except (OSError, KeyboardInterrupt, Stop):
        print("更新処理は確定済みです。完了記録の片付けだけが残りました: " + str(finished), file=sys.stderr)
    return committed


def recover(ws):
    if not journal_path(ws).exists() and not is_link(journal_path(ws)):
        print("中断した更新はありません")
        return
    with update_lock(ws):
        record = load_record(ws)
        try:
            committed = verify_recovery(ws, record)
        except Stop as error:
            raise Stop(str(error), 7)
        info = {"new_ver": "中断更新の復旧", "plan": record["plan"], "approval": record["approval"],
                "package": record["package"], "expected": record["expected"],
                "recovery": "成立済みの更新commitを検査し、対象indexだけを整えます。" if committed else "中断更新の対象だけを更新前へ戻します。履歴は変更しません。"}
        print(f"復旧対象: {', '.join(record['before'])} / plan {record['plan']}", flush=True)
        if ask_human([], info, ws) != "yes":
            raise Stop("本人の承認がないので復旧していません", 6)
        finish_transaction(ws, record)
        print("更新commitの完了を確認しました" if committed else "中断した更新の対象だけを元に戻しました（履歴は変更なし）")


def apply(ws, new, steps, overwrite, merged, info, recheck):
    changed = {rel for rel, _, custom in steps if custom}
    need = changed - overwrite
    if need:
        raise Stop("ワークスペースで書き換えられた OS のファイルがあります。本人に違いを見せ、置き換えてよければ "
                   + " ".join(f"--overwrite {rel}" for rel in sorted(need)) + " を付けてください", 5)
    if overwrite - changed:
        raise Stop("--overwriteに今回の変更対象でない名前があります。checkからやり直してください", 4)
    info["approval"] = fingerprint({"plan": info["plan"], "overwrite": sorted(overwrite)})
    for rel, state in info["expected"].items():
        if rel.endswith(".py"):
            try:
                compile(state_bytes(state), rel, "exec")
            except (SyntaxError, ValueError) as error:
                raise Stop(f"新版のPython構文が不正です。実行も適用もしません: {rel}: {error}")
    answer = ask_human(steps, info, ws)
    if answer != "yes":
        raise Stop(f"本人の承認がないので、何も変えていません（{answer}）", 6)
    if not recheck():
        raise Stop("確認の窓を出している間にワークスペースか新しい版が変わったので、何も変えていません。check からやり直してください", 4)
    with update_lock(ws):
        if not recheck():
            raise Stop("承認後に状態が変わりました。checkからやり直してください", 4)
        path = journal_path(ws)
        paths = list(info["expected"])
        directories = sorted({parent.as_posix() for rel in paths for parent in Path(rel).parents if parent != Path(".") and not (ws / parent).exists()})
        record = {"format": 1, "workspace": str(ws), "head": info["head"], "head_ref": info["head_ref"], "plan": info["plan"], "approval": info["approval"], "runner": sha(RUNNER_BYTES),
                  "package": info["package"], "before": {rel: info["before"][rel] for rel in paths}, "expected": info["expected"],
                  "index": {rel: info["index"][rel] for rel in paths}, "expected_index": {}, "directories": directories}
        for rel, state in info["expected"].items():
            digest = git(ws, "hash-object", "-w", "--stdin", input=state_bytes(state)).strip()
            mode = info["git_modes"][rel] if WINDOWS else "100755" if state["mode"] & 0o111 else "100644"
            record["expected_index"][rel] = [mode, digest]
        prepared = Path(tempfile.mkdtemp(prefix=JOURNAL + "-prepare-", dir=path.parent))
        put(prepared / "recover.py", RUNNER_BYTES, 0o600)
        save_record(prepared, record)
        os.rename(prepared, path)
        print(f"中断時の旧版復旧入口: python3 -I '{path / 'recover.py'}' recover --ws '{ws}'", flush=True)
        try:
            env = {"GIT_INDEX_FILE": str(path / "index")}
            git(ws, "read-tree", record["head"], env=env)
            for rel, (mode, digest) in record["expected_index"].items():
                git(ws, "update-index", "--add", "--cacheinfo", mode, digest, rel, env=env)
            expected_tree = git(ws, "write-tree", env=env).strip()
            for rel, state in record["expected"].items():
                verify_recovery(ws, record)
                (ws / rel).parent.mkdir(parents=True, exist_ok=True)
                replace_state(ws, path, rel, state)
            verify_recovery(ws, record)
            git(ws, "hook", "run", "--ignore-missing", "pre-commit", env=env)
            verify_applied(ws, record)
            if git(ws, "write-tree", env=env).strip() != expected_tree:
                raise Stop("pre-commitが承認されたindexを変更しました。commitしません", 7)
            record["commit"] = git(ws, "-c", "commit.gpgsign=false", "commit-tree", expected_tree, "-p", record["head"],
                                   "-m", f"OS の更新: {len(steps)} ファイル（tools/update_os.py・本人が確認の窓で承認）\n\nBuilder-OS-Plan: {record['plan']}", env=env).strip()
            save_record(path, record)
            verify_applied(ws, record)
            git(ws, "update-ref", "-m", "Builder OS update", record["head_ref"], record["commit"], record["head"])
            finish_transaction(ws, record)
        except BaseException as error:
            try:
                committed = finish_transaction(ws, record)
            except BaseException as recovery_error:
                raise Stop(f"更新を停止しました（{error}）。復旧記録を保持します。旧版recover.pyから確認してください: {recovery_error}", 7)
            if not committed:
                raise Stop(f"途中で失敗したので、書いたファイルを元に戻しました（{error}）", 3)
        done = git(ws, "rev-parse", "--short", "HEAD").strip()
        print(f"できました: 本人が確認の窓で承認したので、{len(steps)} ファイルを新しくして commit しました（{done}）")
        print("wiki/（README.mdを除く）・projects/・recipes/・独自スキルは変えていません")
        print(f"取り消すとき: git revert --no-edit {done}")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    def interrupted(number, frame):
        raise Stop(f"シグナル {number} で更新が中断されました", 7)
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupted)
    ap = argparse.ArgumentParser(description="kote2 Builder AI OS の本体を新しい版にする")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "apply"):
        s = sub.add_parser(name)
        s.add_argument("--from", dest="src", required=True)
        s.add_argument("--ws", default=".")
        if name == "apply":
            s.add_argument("--plan", required=True)
            s.add_argument("--overwrite", action="append", default=[])
    m = sub.add_parser("manifest")
    m.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    m.add_argument("--version")
    m.add_argument("--check", action="store_true")
    recovery = sub.add_parser("recover")
    recovery.add_argument("--ws", default=".")
    a = ap.parse_args()
    try:
        if a.cmd == "manifest":
            root = Path(a.root).resolve()
            text = make_manifest(root, a.version)
            cur = (root / MANIFEST).read_text(encoding="utf-8") if (root / MANIFEST).is_file() else ""
            if a.check:
                if text != cur:
                    raise Stop(f"{MANIFEST} が古いです（python3 tools/update_os.py manifest で作り直す）", 3)
                print("OS のファイルの一覧は新しいです")
                return 0
            (root / MANIFEST).write_text(text, encoding="utf-8")
            n = sum(1 for l in text.splitlines() if l and not l.startswith(("#", "version:", "old ")))
            print(f"{MANIFEST} を作りました（{n} ファイル・昔の版 {text.count(chr(10) + 'old ')} 件）")
            return 0
        if a.cmd == "recover":
            if WINDOWS and not no_links(Path(a.ws).absolute(), "."):
                raise Stop("ワークスペースまたは親がリンクです", 7)
            ws = Path(a.ws).resolve()
            if Path(git(ws, "rev-parse", "--show-toplevel").strip()).resolve() != ws:
                raise Stop("ワークスペースのいちばん上で復旧してください", 2)
            recover(ws)
            return 0
        if WINDOWS and any(not no_links(path.absolute(), ".") for path in (Path(a.ws), Path(a.src).expanduser())):
            raise Stop("ワークスペース・新版または親がリンクです")
        ws, new = Path(a.ws).resolve(), Path(a.src).expanduser().resolve()
        if ws == new:
            raise Stop("新しい版のフォルダとワークスペースが同じです", 2)
        check_ws(ws)
        steps, pid, merged, info = plan(ws, new)
        if a.cmd == "check":
            show(steps, pid, info)
            return 0
        if a.plan != pid:
            raise Stop("計画の番号が違います（check を見せたあとに何か変わりました）。check からやり直してください", 4)
        if steps is None:
            print("変わるファイルはありません（もう新しい版です）")
            return 0
        apply(ws, new, steps, set(a.overwrite), merged, info, lambda: plan(ws, new)[1] == pid)
        return 0
    except Stop as e:
        print(f"止めました: {e}", file=sys.stderr)
        return e.code
    except (OSError, ValueError) as error:
        print(f"止めました: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""公式Gitの固定commitを取得・検査。信頼済み旧版だけを実行する。"""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

WINDOWS = os.name == "nt"
OFFICIAL_REPOSITORY = "kote2kote/kote2-builder-ai-os"
OFFICIAL_REPOSITORY_ID = "1435376611"
INVENTORY = "release-files.json"
MANIFEST = "tools/os-files.txt"
MAX_FILES = 512
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_ZIP = 16 * 1024 * 1024
AUTO_INTERVAL = 24 * 60 * 60
AUTO_TIMEOUT = 8
AUTO_DIRECTORY = "tools/.state/os-update"
ROOT_FILES = {"AGENTS.md", "CLAUDE.md", "README.md", "DESIGN.md", ".gitignore", ".claude/settings.json",
              "VERSION", "LICENSE", "NOTICE", "THIRD_PARTY.md", "CONTRIBUTING.md", INVENTORY}
OS_ROOT_FILES = {"VERSION", "AGENTS.md", "CLAUDE.md", "README.md", "DESIGN.md", ".gitignore", ".claude/settings.json"}
SEEDS = {"wiki/README.md", "wiki/index.md", "wiki/me/profile.md", "wiki/me/proposals.md"}
NAVIGATION_SEEDS = {"wiki/notes/index.md", "wiki/projects/index.md"}
STABLE_DOCUMENTS = {"LICENSE", "NOTICE", "THIRD_PARTY.md", "CONTRIBUTING.md"}
STABLE_VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
LEGACY_VERSION = r"[0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]+"
VERSION = rf"(?:{STABLE_VERSION}|{LEGACY_VERSION})"
BUNDLED_RECIPE_FILES = {
    "recipes/README.md", "recipes/official/utils/claude-docker-sandbox.md",
    "recipes/official/utils/sandbox-handson.md", "recipes/official/web/file-bin.md",
    "recipes/official/web/html-share-board.md", "recipes/official/web/manga-koma-search.md",
    "recipes/official/web/notion-wp.md",
}
BUNDLED_RECIPE_DIRS = (
    "recipes/official/web/ai-search-knowledge/", "recipes/official/builder/explainer-video/",
    "recipes/official/automation/n8n-home-tunnel/", "recipes/official/automation/omni-chatbot/",
)


def is_bundled_recipe(name):
    return name in BUNDLED_RECIPE_FILES or name.startswith(BUNDLED_RECIPE_DIRS)


class PackageError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise PackageError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def version_order(value):
    require(isinstance(value, str) and re.fullmatch(VERSION, value), "版の形式が不正です")
    return (1 if re.fullmatch(STABLE_VERSION, value) else 0, *map(int, re.split(r"[-.]", value)))


def product_version(root):
    data, mode = checked_bytes(Path(root) / "VERSION")
    require(mode == 0o644, "VERSIONのmodeは0644が必要です")
    try:
        value = data.decode("ascii")
    except UnicodeError as error:
        raise PackageError("VERSIONは安定版番号1行が必要です") from error
    require(re.fullmatch(STABLE_VERSION + r"\n?", value), "VERSIONは安定版番号1行が必要です")
    return value.removesuffix("\n")


def json_bytes(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "JSONに重複キーがあります")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=unique, parse_constant=lambda value: require(False, "JSON定数が不正です"))
    except (ValueError, UnicodeError) as error:
        raise PackageError("JSONの形式を確認できません") from error


def valid_path(name):
    require(isinstance(name, str) and len(name) <= 240 and re.fullmatch(r"[A-Za-z0-9._/-]+", name), "不正な配布パスです")
    parts = name.split("/")
    require(all(part not in {"", ".", ".."} for part in parts), "不正な配布パスです")
    require(all(part.lower() not in {".git", ".hg", ".svn", "__pycache__", ".ds_store", ".state"}
                and not part.lower().startswith(".env") for part in parts), "配布できないパスです")
    require(name in ROOT_FILES or name in SEEDS or name in NAVIGATION_SEEDS or name == "projects/.gitkeep"
            or name.startswith("tools/") or is_bundled_recipe(name), "配布範囲外のファイルです")


def no_links(path):
    path = Path(path).absolute()
    for current in (path, *path.parents) if WINDOWS else (path,):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            return False
    return True


def safe_open(path, flags, mode=0o600):
    """リンクを拒否し、内容へ触る前にパスとdescriptorの実体を照合する。"""
    path = Path(path)
    require(not flags & os.O_TRUNC and no_links(path), "リンクまたは安全に開けないファイルです")
    try:
        before = path.lstat()
    except FileNotFoundError:
        before = None
        if not flags & os.O_CREAT:
            raise
        flags |= os.O_EXCL
    require(before is None or stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "通常ファイルではないかハードリンクです")
    flags |= os.O_BINARY if WINDOWS else os.O_NOFOLLOW
    descriptor = os.open(path, flags, mode)
    try:
        opened = os.fstat(descriptor)
        require(no_links(path) and stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1
                and opened.st_ino and os.path.samestat(opened, path.lstat())
                and (before is None or os.path.samestat(before, opened)), "開く間にファイルの実体が変わりました")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def set_mode(descriptor, path, mode):
    if not WINDOWS:
        os.fchmod(descriptor, mode)
        return
    require(no_links(path) and os.path.samestat(os.fstat(descriptor), Path(path).lstat()), "権限設定先の実体が変わりました")
    require(mode in (0o600, 0o644, 0o755) and os.fstat(descriptor).st_mode & stat.S_IWRITE,
            "Windowsで表現できないmodeまたは読取専用ファイルです")


def checked_bytes(path, limit=MAX_FILE):
    with os.fdopen(safe_open(path, os.O_RDONLY), "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit, "通常ファイル・大きさを確認できません")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    require(len(data) <= limit and (before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode)
            == (after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode), "読取り中にファイルが変わりました")
    mode = (0o644 if after.st_mode & stat.S_IWRITE else 0o444) if WINDOWS else stat.S_IMODE(after.st_mode)
    return data, mode


def read_tree(root):
    root = Path(root)
    require(no_links(root) and root.is_dir(), "配布ルートが通常のフォルダではありません")
    result, folded, total = {}, set(), 0
    for path in sorted(root.rglob("*")):
        require(no_links(path), "リンクを配布できません")
        if path.is_dir():
            continue
        name = path.relative_to(root).as_posix()
        valid_path(name)
        require(name.lower() not in folded, "大文字小文字が衝突しています")
        folded.add(name.lower())
        data, mode = checked_bytes(path)
        require(mode in {0o644, 0o755}, "配布modeは0644/0755だけです")
        total += len(data)
        require(len(result) < MAX_FILES and total <= MAX_TOTAL, "配布サイズ・個数の上限を超えました")
        result[name] = {"sha256": digest(data), "mode": mode}
    return result


def check_names(names):
    kinds = {}
    for name in names:
        for index, part in enumerate(name.split("/")):
            prefix = "/".join(name.split("/")[:index + 1])
            kind = "file" if prefix == name else "directory"
            key = prefix.lower()
            require(key not in kinds or kinds[key] == (prefix, kind), "パスの大文字小文字・種類が衝突しています")
            kinds[key] = (prefix, kind)


def manifest(root, tree):
    raw, _ = checked_bytes(Path(root) / MANIFEST)
    files, versions, old = {}, [], set()
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise PackageError("OS一覧はUTF-8である必要があります") from error
    for line in lines:
        if not line or line.startswith("#"):
            continue
        if line.startswith("version: "):
            versions.append(line[9:])
            continue
        match = re.fullmatch(r"(old )?([0-9a-f]{64})  (.+)", line)
        require(match is not None, "OS一覧の構文が不正です")
        historical, checksum, name = match.groups()
        valid_path(name)
        require(name != MANIFEST and (name.startswith("tools/") or name in OS_ROOT_FILES or name == "wiki/README.md"), "OS一覧の対象が不正です")
        if historical:
            require((name, checksum) not in old, "old行が重複しています")
            old.add((name, checksum))
        else:
            require(name not in files, "OS一覧が重複しています")
            files[name] = checksum
    require(len(versions) == 1 and re.fullmatch(VERSION, versions[0]), "OS一覧の版が不正です")
    if re.fullmatch(STABLE_VERSION, versions[0]):
        require(STABLE_DOCUMENTS <= set(tree), "安定版のライセンス・通知・受付文書が足りません")
    if re.fullmatch(STABLE_VERSION, versions[0]) or "VERSION" in tree:
        require("VERSION" in tree and product_version(root) == versions[0], "VERSIONとOS一覧の版が一致しません")
    expected = {name for name in tree if name != MANIFEST and
                (name.startswith("tools/") or name in OS_ROOT_FILES or name == "wiki/README.md")}
    require(set(files) == expected, "OS一覧と配布対象集合が一致しません")
    require(all(name in files for name, checksum in old), "old行の対象がOS一覧にありません")
    require(all(tree[name]["sha256"] == checksum for name, checksum in files.items()), "OS一覧のhashが一致しません")
    return versions[0]


def inspect(root):
    tree = read_tree(root)
    check_names(tree)
    require({MANIFEST, INVENTORY, "AGENTS.md", "CLAUDE.md", "README.md", "DESIGN.md", ".gitignore",
             ".claude/settings.json", "tools/update_os.py", "tools/release_package.py"} | SEEDS <= set(tree), "配布の必須ファイルが足りません")
    data, _ = checked_bytes(Path(root) / INVENTORY)
    inventory = json_bytes(data)
    require(isinstance(inventory, dict) and set(inventory) == {"format", "version", "files"}
            and type(inventory["format"]) is int and inventory["format"] == 1, "配布一覧の形式が不正です")
    expected = {name: entry for name, entry in tree.items() if name != INVENTORY}
    require(isinstance(inventory["files"], dict) and all(isinstance(entry, dict) and set(entry) == {"sha256", "mode"}
            and type(entry["mode"]) is int and isinstance(entry["sha256"], str) for entry in inventory["files"].values()), "配布一覧の項目型が不正です")
    if WINDOWS:
        require(set(inventory["files"]) == set(expected), "配布一覧の集合が一致しません")
        for name, entry in inventory["files"].items():
            require(entry["mode"] in {0o644, 0o755} and entry["sha256"] == expected[name]["sha256"]
                    and expected[name]["mode"] == 0o644, "配布一覧のhash/modeが一致しません")
    else:
        require(inventory["files"] == expected, "配布一覧の集合・hash・modeが一致しません")
    require(inventory["version"] == manifest(root, tree), "2つの一覧の版が一致しません")
    return inventory


def write_inventory(root):
    require(not WINDOWS, "配布一覧の作成にはPOSIXのmodeを保持できる環境が必要です")
    root = Path(root)
    tree = read_tree(root)
    version = manifest(root, tree)
    tree.pop(INVENTORY, None)
    data = (json.dumps({"format": 1, "version": version, "files": tree}, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode()
    path = root / INVENTORY
    require(not path.is_symlink(), "配布一覧がリンクです")
    path.write_bytes(data)
    path.chmod(0o644)


def make_zip(root, output):
    require(not WINDOWS, "配布ZIPの作成にはPOSIXのmodeを保持できる環境が必要です")
    root, output = Path(root), Path(output)
    metadata = inspect(root)
    inventory_data, inventory_mode = checked_bytes(root / INVENTORY)
    require(json_bytes(inventory_data) == metadata, "検査後に配布一覧が変わりました")
    expected = {**metadata["files"], INVENTORY: {"sha256": digest(inventory_data), "mode": inventory_mode}}
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_STORED) as archive:
        require(read_tree(root) == expected, "梱包前に配布物が変わりました")
        for name, entry in expected.items():
            data, mode = checked_bytes(root / name)
            require(digest(data) == entry["sha256"] and mode == entry["mode"], "梱包中に配布物が変わりました")
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, data)


def safe_extract(zip_path, destination):
    if isinstance(zip_path, bytes):
        data = zip_path
    else:
        data, _ = checked_bytes(Path(zip_path), MAX_ZIP)
    require(len(data) <= MAX_ZIP, "ZIPが大きすぎます")
    destination = Path(destination)
    require(no_links(destination), "展開先または親がリンクです")
    require(not os.path.lexists(destination), "展開先は新しい空の場所に限ります")
    snapshots, folded, total = {}, set(), 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            require(0 < len(entries) <= MAX_FILES, "ZIPの個数上限を超えました")
            for entry in entries:
                name = entry.filename
                require(entry.orig_filename == name and not entry.is_dir(), "ZIPの名前・種類が不正です")
                valid_path(name)
                require(name.lower() not in folded, "ZIPの名前が重複・衝突しています")
                folded.add(name.lower())
                mode = entry.external_attr >> 16
                require(entry.create_system == 3 and stat.S_ISREG(mode) and stat.S_IMODE(mode) in {0o644, 0o755}, "ZIPは通常ファイル0644/0755だけです")
                total += entry.file_size
                require(entry.file_size <= MAX_FILE and total <= MAX_TOTAL and not entry.flag_bits & 1,
                        "ZIPのサイズ・暗号化が許可されません")
                require(entry.file_size <= max(entry.compress_size, 1) * 200, "ZIPの圧縮率が高すぎます")
                snapshots[name] = (archive.read(entry), stat.S_IMODE(mode))
        check_names(snapshots)
        destination.mkdir(mode=0o700)
        for name, (content, mode) in snapshots.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            require(no_links(path.parent), "展開先の親がリンクです")
            with os.fdopen(safe_open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "wb") as stream:
                stream.write(content)
                set_mode(stream.fileno(), path, mode)
        metadata = inspect(destination)
        require(all(name == INVENTORY or mode == metadata["files"][name]["mode"]
                    for name, (content, mode) in snapshots.items()), "ZIPと配布一覧のmodeが一致しません")
        return metadata
    except BaseException:
        if no_links(destination) and destination.is_dir():
            shutil.rmtree(destination)
        raise


def run_gh(binary, args, environment, timeout=120):
    result = subprocess.run([binary, *args], env=environment, capture_output=True, timeout=timeout)
    require(result.returncode == 0, "GitHub CLIの検証/認証/取得に失敗しました。検証を省略できません")
    require(len(result.stdout) <= MAX_TOTAL, "GitHub CLIの応答が大きすぎます")
    return result.stdout


def statement(output, repository, repository_id, tag, release_id, ref_sha):
    result = json_bytes(output)
    require(isinstance(result, dict) and isinstance(result.get("verificationResult"), dict), "CLI検証結果がありません")
    try:
        envelope = result["attestation"]["bundle"]["dsseEnvelope"]
        require(envelope["payloadType"] == "application/vnd.in-toto+json", "attestation形式が違います")
        payload = json_bytes(base64.b64decode(envelope["payload"], validate=True))
        require(payload["_type"] == "https://in-toto.io/Statement/v1"
                and payload["predicateType"] == "https://in-toto.io/attestation/release/v0.1", "Release attestationではありません")
        predicate = payload["predicate"]
        require(predicate["repository"] == repository and predicate["repositoryId"] == repository_id
                and predicate["tag"] == tag and predicate["releaseId"] == str(release_id)
                and predicate["purl"] == f"pkg:github/{repository}@{tag}", "署名済みRelease identityが一致しません")
        subjects = payload["subject"]
        algorithm = "sha1" if len(ref_sha) == 40 else "sha256"
        matches = [subject for subject in subjects if subject.get("uri") == f"pkg:github/{repository}@{tag}"
                   and subject.get("digest") == {algorithm: ref_sha}]
        require(len(matches) == 1, "署名済みtagの参照が一致しません")
        return payload
    except (KeyError, TypeError, ValueError) as error:
        raise PackageError("CLIの署名済みJSON形式を確認できません") from error


def fetch_release(tag, workspace):
    """旧ZIP経路の互換API。通常のfetchからは呼ばない。"""
    repository, repository_id = OFFICIAL_REPOSITORY, OFFICIAL_REPOSITORY_ID
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) and re.fullmatch(r"[1-9][0-9]*", repository_id), "公式リポジトリが未設定です。通信せず停止します")
    require(re.fullmatch("v" + STABLE_VERSION, tag), "明示した安定版vMAJOR.MINOR.PATCHタグが必要です（日付版は読込互換のみ）")
    require(no_links(workspace), "ワークスペースまたは親がリンクです")
    workspace = Path(workspace).resolve()
    require(workspace.is_dir(), "ワークスペースがありません")
    old_raw, _ = checked_bytes(workspace / MANIFEST)
    previous = re.findall(rb"^version: (.+)$", old_raw, re.M)
    require(len(previous) == 1 and re.fullmatch(VERSION, previous[0].decode()), "ワークスペースの版が不正です")
    if re.fullmatch(STABLE_VERSION, previous[0].decode()) or (workspace / "VERSION").exists() or (workspace / "VERSION").is_symlink():
        require(product_version(workspace) == previous[0].decode(), "VERSIONとワークスペースの版が一致しません")
        version_hashes = re.findall(rb"^([0-9a-f]{64})  VERSION$", old_raw, re.M)
        require(version_hashes == [digest(checked_bytes(workspace / "VERSION")[0]).encode()], "VERSIONとOS一覧のhashが一致しません")
    require(version_order(tag[1:]) > version_order(previous[0].decode()), "同じ版・古い版へは更新しません")
    binary = shutil.which("gh")
    require(binary is not None, "GitHub CLI 2.102.0以降の修正版が必要です")
    environment = {key: value for key, value in os.environ.items() if key in
                   {"HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "GH_TOKEN", "GITHUB_TOKEN", "SSL_CERT_FILE", "SSL_CERT_DIR"}}
    environment.update({"GH_HOST": "github.com", "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "GH_PAGER": "cat"})
    version = run_gh(binary, ["--version"], environment).decode().splitlines()[0]
    match = re.fullmatch(r"gh version ([0-9]+)\.([0-9]+)\.([0-9]+)(?: \([^\r\n]+\))?", version)
    require(match is not None and tuple(map(int, match.groups())) >= (2, 102, 0), "GitHub CLI 2.102.0以降の安定修正版が必要です")
    run_gh(binary, ["auth", "status", "--hostname", "github.com"], environment)
    def api(path):
        return json_bytes(run_gh(binary, ["api", "--hostname", "github.com", f"repos/{repository}/{path}".rstrip("/")], environment))
    identity = api("")
    require(str(identity.get("id")) == repository_id and identity.get("full_name") == repository
            and identity.get("private") is False, "公式リポジトリのidentityが一致しません")
    release = api(f"releases/tags/{tag}")
    require(release.get("tag_name") == tag and release.get("draft") is False
            and release.get("prerelease") is False and release.get("immutable") is True
            and type(release.get("id")) is int, "正式なImmutable Releaseを確認できません")
    ref = api(f"git/ref/tags/{tag}")
    ref_sha = ref.get("object", {}).get("sha", "")
    require(ref.get("ref") == f"refs/tags/{tag}" and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", ref_sha), "tag参照が不正です")
    commit = api(f"commits/{tag}").get("sha", "")
    require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit), "公開commitを確認できません")
    target = ref.get("object", {})
    for depth in range(8):
        if target.get("type") != "tag":
            break
        annotated = api("git/tags/" + target["sha"])
        require(annotated.get("sha") == target["sha"], "注釈tagの参照が一致しません")
        target = annotated.get("object", {})
    require(target.get("type") == "commit" and target.get("sha") == commit, "tagと公開commitが一致しません")
    flags = ["--repo", "github.com/" + repository, "--format", "json"]
    verified = statement(run_gh(binary, ["release", "verify", tag, *flags], environment), repository, repository_id, tag, release["id"], ref_sha)
    name = f"builder-os-{tag}.zip"
    assets = [asset for asset in release.get("assets", []) if asset.get("name") == name]
    require(len(assets) == 1, "専用配布ZIPが一つだけ必要です")
    asset = assets[0]
    require(asset.get("state") == "uploaded" and type(asset.get("size")) is int and 0 < asset["size"] <= MAX_ZIP
            and re.fullmatch(r"sha256:[0-9a-f]{64}", asset.get("digest", "")), "専用ZIPのmetadataが不正です")
    checksum = asset["digest"][7:]
    require(sum(subject.get("name") == name and subject.get("digest") == {"sha256": checksum}
                for subject in verified["subject"]) == 1, "署名済みasset名とhashが一致しません")
    folder = Path(tempfile.mkdtemp(prefix="builder-os-release-")).resolve()
    try:
        require(not folder.is_relative_to(workspace), "取得先がワークスペース内です")
        download = folder / "download"
        download.mkdir(mode=0o700)
        run_gh(binary, ["release", "download", tag, "--repo", "github.com/" + repository,
                        "--pattern", name, "--dir", str(download)], environment)
        require(sorted(path.name for path in download.iterdir()) == [name], "専用ZIP以外を取得しました")
        data, _ = checked_bytes(download / name, MAX_ZIP)
        require(len(data) == asset["size"] and digest(data) == checksum, "取得ZIPのhash/sizeが一致しません")
        verified_asset = statement(run_gh(binary, ["release", "verify-asset", tag, str(download / name), *flags], environment),
                                   repository, repository_id, tag, release["id"], ref_sha)
        require(verified_asset == verified and checked_bytes(download / name, MAX_ZIP)[0] == data, "検証中にZIP/attestationが変わりました")
        package = folder / "package"
        metadata = safe_extract(data, package)
        verified_tree = read_tree(package)
        require(metadata["version"] == tag[1:], "tagと配布物の版が一致しません")
        require(checked_bytes(workspace / MANIFEST)[0] == old_raw, "取得の間にワークスペースの版が変わりました")
        runner = workspace / "tools/update_os.py"
        require(no_links(runner) and runner.is_file(), "信頼済み旧版更新器が必要です")
        checked = subprocess.run([sys.executable, "-I", str(runner), "check", "--from", str(package), "--ws", str(workspace)], capture_output=True, text=True, encoding="utf-8", timeout=120)
        require(checked.returncode == 0, "旧版のcheckで停止しました: " + checked.stdout + checked.stderr)
        require(inspect(package) == metadata and read_tree(package) == verified_tree, "旧版checkの間に検証済み配布物が変わりました")
        plans = re.findall(r"^plan ([0-9a-f]{12})$", checked.stdout, re.M)
        require(len(plans) == 1, "旧版checkのplanを取得できません")
        print(checked.stdout, end="")
        receipt = {"repository": repository, "repository_id": repository_id, "tag": tag, "ref": ref_sha,
                   "commit": commit, "sha256": checksum, "inventory_sha256": digest((package / INVENTORY).read_bytes()),
                   "plan": plans[0], "package": str(package)}
        (folder / "verified.json").write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
        return receipt
    except BaseException:
        shutil.rmtree(folder)
        raise


def run_git(binary, args, environment):
    result = subprocess.run([binary, "-c", "core.hooksPath=" + os.devnull,
                             "-c", "credential.helper=", "-c", "protocol.allow=never",
                             "-c", "protocol.https.allow=always", "-c", "http.followRedirects=false",
                             "-c", "fetch.fsckObjects=true", "-c", "transfer.fsckObjects=true",
                             *args], env=environment, capture_output=True, timeout=120)
    require(result.returncode == 0, "公式Gitの取得・検査に失敗しました。検査を省略できません")
    require(len(result.stdout) <= MAX_TOTAL, "Gitの応答が大きすぎます")
    return result.stdout


def remote_source(ref=None, deadline=None):
    repository, repository_id = OFFICIAL_REPOSITORY, OFFICIAL_REPOSITORY_ID
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) and re.fullmatch(r"[1-9][0-9]*", repository_id),
            "公式リポジトリが未設定です。通信せず停止します")
    if ref is not None:
        require(isinstance(ref, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", ref)
                and ".." not in ref and "//" not in ref and not ref.endswith("/"), "取得refが不正です")
    binary = shutil.which("gh")
    require(binary is not None, "GitHub CLIが必要です")
    environment = {key: value for key, value in os.environ.items() if key in
                   {"HOME", "PATH", "TMPDIR", "TMP", "TEMP", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL",
                    "GH_TOKEN", "GITHUB_TOKEN", "SSL_CERT_FILE", "SSL_CERT_DIR"}}
    environment.update({"GH_HOST": "github.com", "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "GH_PAGER": "cat"})
    def api(path):
        arguments = ["api", "--hostname", "github.com", f"repos/{repository}/{path}".rstrip("/")]
        if deadline is None:
            return json_bytes(run_gh(binary, arguments, environment))
        remaining = deadline - time.monotonic()
        require(remaining > 0, "版確認の時間制限に達しました")
        return json_bytes(run_gh(binary, arguments, environment, timeout=min(120, remaining)))
    identity = api("")
    require(str(identity.get("id")) == repository_id and identity.get("full_name") == repository
            and identity.get("private") is False, "公式リポジトリのidentityが一致しません")
    if ref is None:
        ref = identity.get("default_branch")
        require(isinstance(ref, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", ref)
                and ".." not in ref and "//" not in ref and not ref.endswith("/"), "公式の既定branchが不正です")
    resolved = api("commits/" + ref)
    commit = resolved.get("sha", "")
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit), "公開commitを確認できません")
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        require(commit == ref, "指定commitと公開commitが一致しません")
    return {"repository": repository, "repository_id": repository_id, "ref": ref, "commit": commit}, binary, environment, api


def workspace_version(workspace):
    require(no_links(workspace), "ワークスペースまたは親がリンクです")
    workspace = Path(workspace).resolve()
    require(workspace.is_dir(), "ワークスペースがありません")
    old_raw, _ = checked_bytes(workspace / MANIFEST)
    previous = re.findall(rb"^version: (.+)$", old_raw, re.M)
    require(len(previous) == 1, "ワークスペースの版が不正です")
    version = previous[0].decode("ascii")
    version_order(version)
    if re.fullmatch(STABLE_VERSION, version) or (workspace / "VERSION").exists() or (workspace / "VERSION").is_symlink():
        require(product_version(workspace) == version, "VERSIONとワークスペースの版が一致しません")
        require(re.findall(rb"^([0-9a-f]{64})  VERSION$", old_raw, re.M)
                == [digest(checked_bytes(workspace / "VERSION")[0]).encode()], "VERSIONとOS一覧のhashが一致しません")
    return version, old_raw


def update_status(workspace=".", ref=None, timeout=None):
    current, old_raw = workspace_version(workspace)
    if timeout is None:
        source, binary, environment, api = remote_source(ref)
    else:
        source, binary, environment, api = remote_source(ref, deadline=time.monotonic() + timeout)
    response = api("contents/VERSION?ref=" + source["commit"])
    require(response.get("type") == "file" and response.get("path") == "VERSION" and response.get("encoding") == "base64"
            and type(response.get("size")) is int and 0 < response["size"] <= 128, "公式VERSIONの情報が不正です")
    content = response.get("content")
    require(isinstance(content, str) and len(content) <= 256, "公式VERSIONの内容が不正です")
    data = base64.b64decode(content.replace("\n", ""), validate=True)
    require(len(data) == response["size"]
            and hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest() == response.get("sha"),
            "公式VERSIONのhash/sizeが一致しません")
    text = data.decode("ascii")
    require(re.fullmatch(STABLE_VERSION + r"\n?", text), "公式VERSIONは安定版番号1行が必要です")
    version = text.removesuffix("\n")
    require(workspace_version(workspace) == (current, old_raw), "確認の間にワークスペースの版が変わりました")
    return {**source, "current_version": current, "version": version, "available": version_order(version) > version_order(current)}


@contextmanager
def auto_lock(directory):
    path = directory / "lock"
    require(no_links(path), "自動確認の保存先がリンクです")
    descriptor = safe_open(path, os.O_RDWR | os.O_CREAT)
    acquired = False
    try:
        metadata = os.fstat(descriptor)
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, "自動確認lockが通常ファイルではありません")
        if metadata.st_size == 0:
            os.write(descriptor, b"0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            if WINDOWS:
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            pass
        yield acquired
    finally:
        if acquired:
            if WINDOWS:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def auto_state(directory):
    path = directory / "check.json"
    require(no_links(path), "自動確認の記録がリンクです")
    if not path.exists():
        return {"format": 1, "enabled": True, "last_attempt": None, "notified_version": None}
    data, _ = checked_bytes(path, 4096)
    state = json_bytes(data)
    require(isinstance(state, dict) and set(state) == {"format", "enabled", "last_attempt", "notified_version"}
            and type(state["format"]) is int and state["format"] == 1
            and type(state["enabled"]) is bool
            and (state["last_attempt"] is None or type(state["last_attempt"]) is int and state["last_attempt"] >= 0)
            and (state["notified_version"] is None or isinstance(state["notified_version"], str)
                 and re.fullmatch(STABLE_VERSION, state["notified_version"])), "自動確認の記録形式が不正です")
    return state


def save_auto_state(directory, state):
    require(no_links(directory / "check.json"), "自動確認の記録がリンクです")
    descriptor, temporary = tempfile.mkstemp(prefix="check-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(state, sort_keys=True) + "\n")
        os.replace(temporary, directory / "check.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def auto_directory(workspace):
    """Keep legacy settings in place; never choose between conflicting stores."""
    current = workspace / AUTO_DIRECTORY
    legacy = workspace / ".builder-os-update"
    existing = [path for path in (current, legacy) if os.path.lexists(path)]
    require(len(existing) <= 1, "自動確認の保存先が複数あります。旧記録と新記録を確認してください")
    directory = existing[0] if existing else current
    for path in (*reversed(directory.parents), directory):
        require(no_links(path), "自動確認の保存先または親がリンクです")
        require(not path.exists() or path.is_dir(), "自動確認の保存先または親が通常フォルダではありません")
    return directory


def automatic_status(workspace=".", enabled=None):
    quiet = {"notify": False}
    try:
        workspace_version(workspace)
        directory = auto_directory(Path(workspace).resolve())
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with auto_lock(directory) as acquired:
            if not acquired:
                return {**quiet, "status": "skipped", "reason": "busy"}
            state = auto_state(directory)
            if enabled is not None:
                state["enabled"] = enabled
                save_auto_state(directory, state)
                return {**quiet, "status": "configured", "enabled": enabled}
            if not state["enabled"]:
                return {**quiet, "status": "skipped", "reason": "disabled"}
            now = int(time.time())
            previous = state["last_attempt"]
            if previous is not None and now < previous:
                return {**quiet, "status": "skipped", "reason": "clock_rollback"}
            if previous is not None and now - previous < AUTO_INTERVAL:
                return {**quiet, "status": "skipped", "reason": "interval"}
            state["last_attempt"] = now
            save_auto_state(directory, state)
            result = update_status(workspace, timeout=AUTO_TIMEOUT)
            notified = state["notified_version"]
            notify = result["available"] and (notified is None or version_order(result["version"]) > version_order(notified))
            if notify:
                state["notified_version"] = result["version"]
                save_auto_state(directory, state)
            return {**result, "status": "checked", "notify": notify}
    except (PackageError, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, subprocess.SubprocessError):
        return {**quiet, "status": "unknown", "reason": "check_unavailable"}


def extract_commit(binary, repository, commit, destination, environment):
    prefix = ["--git-dir", str(repository)]
    listing = run_git(binary, [*prefix, "ls-tree", "-r", "-l", "-z", "--full-tree", commit], environment)
    entries, total = {}, 0
    for record in listing.split(b"\0"):
        if not record:
            continue
        header, name_bytes = record.split(b"\t", 1)
        mode, kind, object_id, size_bytes = header.split()
        name = name_bytes.decode("ascii")
        valid_path(name)
        require(name not in entries and mode in {b"100644", b"100755"} and kind == b"blob",
                "Git treeは通常ファイル0644/0755だけです")
        require(re.fullmatch(rb"[0-9a-f]{40}", object_id) and size_bytes.isdigit(), "Git blob情報が不正です")
        size = int(size_bytes)
        total += size
        require(size <= MAX_FILE and total <= MAX_TOTAL and len(entries) < MAX_FILES, "配布サイズ・個数の上限を超えました")
        entries[name] = (int(mode, 8) & 0o777, object_id.decode("ascii"), size)
    require(entries, "Git treeが空です")
    check_names(entries)
    destination.mkdir(mode=0o700)
    for name, (mode, object_id, size) in entries.items():
        data = run_git(binary, [*prefix, "cat-file", "blob", object_id], environment)
        require(len(data) == size and hashlib.sha1(b"blob " + str(size).encode("ascii") + b"\0" + data).hexdigest() == object_id,
                "Git blobのhash/sizeが一致しません")
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(safe_open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as stream:
            stream.write(data)
            set_mode(stream.fileno(), path, mode)


def fetch(tag=None, workspace=".", ref=None):
    repository, repository_id = OFFICIAL_REPOSITORY, OFFICIAL_REPOSITORY_ID
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) and re.fullmatch(r"[1-9][0-9]*", repository_id),
            "公式リポジトリが未設定です。通信せず停止します")
    require(tag is None or re.fullmatch("v" + STABLE_VERSION, tag), "明示した安定版vMAJOR.MINOR.PATCHタグが必要です")
    require(tag is None or ref is None, "tagとrefは同時に指定できません")
    requested = tag if tag is not None else ref
    if requested is not None:
        require(isinstance(requested, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", requested)
                and ".." not in requested and "//" not in requested and not requested.endswith("/"), "取得refが不正です")
    old_version, old_raw = workspace_version(workspace)
    workspace = Path(workspace).resolve()
    if tag is not None:
        require(version_order(tag[1:]) > version_order(old_version), "同じ版・古い版へは更新しません")
    git_binary = shutil.which("git")
    require(git_binary is not None, "GitHub CLIとGitが必要です")
    source, binary, environment, api = remote_source(requested)
    requested, commit = source["ref"], source["commit"]
    git_environment = {key: value for key, value in environment.items() if key in
                       {"PATH", "TMPDIR", "TMP", "TEMP", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR"}}
    git_environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                            "GIT_CONFIG_SYSTEM": os.devnull, "GIT_TERMINAL_PROMPT": "0",
                            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_ATTR_NOSYSTEM": "1"})
    folder = Path(tempfile.mkdtemp(prefix="builder-os-git-")).resolve()
    try:
        require(not folder.is_relative_to(workspace), "取得先がワークスペース内です")
        objects = folder / "objects.git"
        run_git(git_binary, ["init", "--bare", "--template=", str(objects)], git_environment)
        prefix = ["--git-dir", str(objects)]
        run_git(git_binary, [*prefix, "fetch", "--depth=1", "--no-tags", "--no-recurse-submodules", "--no-auto-maintenance",
                             "https://github.com/" + repository + ".git", commit], git_environment)
        require(run_git(git_binary, [*prefix, "rev-parse", "--verify", "FETCH_HEAD^{commit}"], git_environment).decode().strip() == commit,
                "取得commitが一致しません")
        run_git(git_binary, [*prefix, "fsck", "--strict", "--no-reflogs"], git_environment)
        package = folder / "package"
        extract_commit(git_binary, objects, commit, package, git_environment)
        metadata = inspect(package)
        require(re.fullmatch(STABLE_VERSION, metadata["version"]), "配布版は安定版番号が必要です")
        require(tag is None or metadata["version"] == tag[1:], "tagと配布物の版が一致しません")
        require(version_order(metadata["version"]) > version_order(old_version), "同じ版・古い版へは更新しません")
        verified_tree = read_tree(package)
        require(checked_bytes(workspace / MANIFEST)[0] == old_raw, "取得の間にワークスペースの版が変わりました")
        runner = workspace / "tools/update_os.py"
        require(no_links(runner) and runner.is_file(), "信頼済み旧版更新器が必要です")
        checked = subprocess.run([sys.executable, "-I", str(runner), "check", "--from", str(package), "--ws", str(workspace)],
                                 capture_output=True, text=True, encoding="utf-8", timeout=120)
        require(checked.returncode == 0, "旧版のcheckで停止しました: " + checked.stdout + checked.stderr)
        require(inspect(package) == metadata and read_tree(package) == verified_tree, "旧版checkの間に検証済み配布物が変わりました")
        plans = re.findall(r"^plan ([0-9a-f]{12})$", checked.stdout, re.M)
        require(len(plans) == 1, "旧版checkのplanを取得できません")
        print(checked.stdout, end="")
        receipt = {"source": "git", "repository": repository, "repository_id": repository_id, "ref": requested,
                   "commit": commit, "version": metadata["version"], "inventory_sha256": digest((package / INVENTORY).read_bytes()),
                   "plan": plans[0], "package": str(package)}
        (folder / "verified.json").write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
        return receipt
    except BaseException:
        shutil.rmtree(folder)
        raise


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("inspect")
    check.add_argument("root")
    obtain = commands.add_parser("fetch")
    selection = obtain.add_mutually_exclusive_group()
    selection.add_argument("--tag")
    selection.add_argument("--ref")
    obtain.add_argument("--ws", default=".")
    status = commands.add_parser("status", help="公式VERSIONだけで更新の有無を確認")
    status.add_argument("--ws", default=".")
    status.add_argument("--ref")
    automatic = commands.add_parser("auto-status", help="24時間ごとの版確認。取得・適用しない")
    automatic.add_argument("--ws", default=".")
    configuration = commands.add_parser("auto-config", help="本人指定による自動確認の切替（通信なし）")
    configuration.add_argument("--ws", default=".")
    configuration.add_argument("--enabled", required=True, choices=("on", "off"))
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            result = inspect(Path(args.root))
        elif args.command == "status":
            result = update_status(args.ws, args.ref)
        elif args.command == "auto-status":
            result = automatic_status(args.ws)
        elif args.command == "auto-config":
            result = automatic_status(args.ws, enabled=args.enabled == "on")
        else:
            result = fetch(args.tag, args.ws, args.ref)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (PackageError, OSError, ValueError, KeyError, TypeError, AttributeError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(f"止めました: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())

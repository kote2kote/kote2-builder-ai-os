#!/usr/bin/env python3
"""kote2 Builder v3 の資産を、このワークスペース（kote2 Builder AI OS）に移す。

  python3 tools/migrate_v3.py scan  --from <v3 のフォルダ> [--full]
  python3 tools/migrate_v3.py prepare --from <v3 のフォルダ>
  python3 tools/migrate_v3.py evaluate --from <v3 のフォルダ> --classification <分類済みJSON>
  python3 tools/migrate_v3.py apply --from <v3 のフォルダ> --classification <最終JSON> --plan <承認hash>

- v3 のフォルダは読むだけ（書かない・消さない・動かさない）。apply の前後で、読んだファイルが同じかを確かめる。
- scan は何も書かない。何がどこへ入るか・何を移さないかを表示し、計画の番号を出す。
- apply は分類計画を作り直し、承認した最終hashと同じときだけ書く。
  全部書けたら1回の commit にする。検出できる例外は復旧し、強制終了後は resume/recover で状態を確かめる。
- 手順（AI 向け）は tools/v3-migration.md。Python の標準の部品だけで動く。
"""
import argparse
import ctypes
import datetime
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import unicodedata
import sys
from types import SimpleNamespace
from pathlib import Path

_topics_spec = importlib.util.spec_from_file_location("v3_topics", Path(__file__).resolve().with_name("v3_topics.py"))
v3_topics = importlib.util.module_from_spec(_topics_spec)
_topics_spec.loader.exec_module(v3_topics)
import stat
import base64
import uuid
from html.parser import HTMLParser
from urllib.parse import quote, unquote

TODAY = datetime.date.today().isoformat()

SKIP_DIRS = {"node_modules", ".git", ".wrangler", ".venv", "venv", "__pycache__",
             ".recipe-test", ".next", ".turbo", ".cache", ".svelte-kit"}
SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}
SECRET_NAME = re.compile(
    r"^(\.env(\..+)?|\.dev\.vars(\..+)?|\.envrc|.+\.(pem|key|p12|pfx)|id_(rsa|ed25519|ecdsa)(\.pub)?"
    r"|.*credentials.*\.json|settings\.local\.json|service[-_]?account.*\.json|\.netrc|\.npmrc|\.pypirc)$",
    re.I)
SAFE_SUFFIX = (".example", ".sample", ".template")
SECRET_TEXT = [
    re.compile(r"(?<![A-Za-z0-9])sk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}"),
    re.compile(r"(?<![A-Za-z0-9])xox[abposr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_\-]{35}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd)['\"]?\s*[:=]\s*['\"](?=[^'\"]*\d)(?=[^'\"]*[a-z])"
               r"(?![^'\"]*(example|your|xxxx|dummy|placeholder))[A-Za-z0-9_\-+/]{24,}['\"]"),
]

# v3 のひな形に最初から入っているお願い（本人が書いたものではないので移さない）
V3_DEFAULT_BEHAVIOR = {
    "非エンジニアにも伝わる言葉で話す(専門用語を出す時は必ず1行説明)",
    "「できません」で打ち切らない(現状仕様 → 拡張案 → 実装可否確認の順で提案)",
    "大きな変更前にはリビジョン保存を提案する",
    "設計書で確認を取ってから生成する",
    "急な方向転換も「できない」で済まさず、設計し直しを前向きに提案する",
    "「ドメイン知識をチェックして」と頼まれたら、`domain-knowledge.md` を読み、不明な点や業務判断に活かしづらい箇所があれば「これってどういうこと?」と質問する。質問を通じて理解した内容は、**ユーザーの許可を得てから**ファイルに追記する(勝手に上書きしない)。",
    "`domain-knowledge.md` が空、またはコメント例(`<!-- (例) ... -->`)のみで本文が書かれていない場合は、以下の定型説明をする:",
    "> このファイルは、あなたの業界・ドメイン知識を AI に渡すための場所です。",
    "> 業務の進め方や大事なポイントを、自分の言葉で自由に書いてください。",
    "> ビルダー直下の `domain-samples/` フォルダに業種別のお手本(SEO など)があるので、参考にできます。",
    "> 何か書き出すお手伝いをしましょうか?",
    "日常の業務支援中も、ユーザーの質問やタスク内容が `domain-knowledge.md` の記述と関連する場合は、必ずそちらの判断基準・地雷・用語定義を優先する(builder.md / 一般知識より優先)。",
}
V3_WORDS = re.compile(r"リビジョン|設計書|builder\.md|\.claude/|output/|レシピ|ダッシュボード|スキル提案"
                      r"|domain-knowledge\.md|aboutme\.md|ai-behavior\.md|生成|ビルダー")
V3_TOOL_STEP = re.compile(r"scripts/(validate-|recipe-|zip-project|sync-docs|wiki-|build-dist|check-sync)"
                          r"|builder\.md|\.project-memory|recipe-test|validate-output|validate-codex"
                          r"|templates/(recipe|codex|hooks|dashboard|project-memory|skill-ideas)")

USER_FILES = ["aboutme.md", "ai-behavior.md", "domain-knowledge.md", "design-knowledge.md"]
V3_SYSTEM_TOP = {
    "builder.md", "AGENTS.md", "CLAUDE.md", "CLAUDE.dev.md", "CLAUDE.live.md", "CLAUDE.dev.distribution.md",
    "README.md", "README.free.md", "README.pro.md", "MIGRATION.md", "NOTICE.md", "TERMS.md", "VERSION",
    "dashboard.html", "manual.html", "templates", "scripts", "usecase", "domain-samples", ".claude", ".codex",
    ".gitignore", ".git", ".gitattributes", ".agents", "aboutme.example.md", "ai-behavior.example.md",
    "domain-knowledge.example.md", "design-knowledge.example.md", "dist",
}
V4_TOP = {"os", "hearings", "exports"}
CARD_DIRS = ["knowledge", "troubleshooting", "decisions", "patterns", "sources", "stacks"]
WIKI_SYSTEM = {"WIKI.md", "index.md", "guide.html", "index.html", "graph.html", "admin", "index.json"}
WIKI_ARCHIVE = {"log.md", "questions.md", "daily", "assets"}


class Stop(Exception):
    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.code = code


# ---------- 小さな道具 ----------

def sha(data):
    return hashlib.sha256(data).hexdigest()


def mdate(p):
    return datetime.date.fromtimestamp(p.stat().st_mtime).isoformat()


def read_text(p):
    try:
        return p.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None


LINKS = []   # v3 の中で見つけたリンク（先は読まない）


def walk(root):
    """root 以下のファイルを、飛ばすフォルダとリンクを除いて順に返す。"""
    if os.path.islink(root):
        LINKS.append(Path(root))
        return
    for dirpath, dirnames, filenames in os.walk(root):
        keep = []
        for d in sorted(dirnames):
            if d in SKIP_DIRS:
                continue
            if os.path.islink(os.path.join(dirpath, d)):
                LINKS.append(Path(dirpath) / d)
                continue
            keep.append(d)
        dirnames[:] = keep
        for f in sorted(filenames):
            p = Path(dirpath) / f
            if f in SKIP_FILES:
                continue
            if p.is_symlink():
                LINKS.append(p)
                continue
            info = p.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise Stop("移行元のhardlinkまたは特殊ファイルは読みません。", 4)
            yield p


def is_secret_name(name):
    if name.lower().endswith(SAFE_SUFFIX):
        return False
    return bool(SECRET_NAME.match(name))


def secret_lines(text):
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if any(r.search(line) for r in SECRET_TEXT):
            hits.append(i)
    return hits


def redact(text):
    """秘密らしい文字列がある行を、印に置き換える。（置き換えた本文, 行番号の一覧）"""
    hits = secret_lines(text)
    if not hits:
        return text, []
    lines = text.split("\n")
    for i in hits:
        lines[i - 1] = "（秘密らしい文字列があったので、この行は移していません）"
    return "\n".join(lines), hits


def safe_dest(ws, v3, rel):
    """ワークスペースの中の書き先が、リンクを通らず、ワークスペースの中にあり、v3 の外にあるかを確かめる。"""
    try:
        v3_topics.relative(rel)
    except ValueError:
        raise Stop("書き先の相対パスに対応しない文字または要素があります。元データは変えず、別のコピーで名前を整えて再計画してください。", 4)
    cur = ws
    for part in Path(rel).parts:
        cur = cur / part
        if cur.is_symlink():
            raise Stop(f"書き先にリンクがあります（安全のため止めました）: {cur.relative_to(ws)}")
        if os.path.lexists(cur):
            info = cur.lstat()
            if not stat.S_ISDIR(info.st_mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise Stop("書き先にhardlinkまたは特殊ファイルがあります（止めました）。", 4)
    real = Path(os.path.realpath(ws / rel))
    wsr, v3r = Path(os.path.realpath(ws)), Path(os.path.realpath(v3))
    if wsr not in real.parents or real == v3r or v3r in real.parents:
        raise Stop(f"書き先がワークスペースの外か v3 の中を指しています（止めました）: {rel}")


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "project"


def yq(s):
    s = str(s).strip()
    if re.search(r"[:#\[\]{}&*!|>'\"%@`]", s) or s != s.strip():
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def split_fm(text):
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for k in range(1, len(lines)):
            if lines[k].strip() == "---":
                return lines[1:k], lines[k + 1:]
    return None, lines


def fm_keys(fm):
    keys = {}
    for line in fm or []:
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            keys[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return keys


def first_h1(lines):
    for line in lines:
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            return m.group(1).strip()
    return None


def norm(line):
    s = re.sub(r"〔[^〕]*〕", "", line)
    s = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", s)
    s = re.sub(r"^【[^】]*】", "", s)
    return re.sub(r"\s+", " ", s).strip()


BULLET = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
KV = re.compile(r"^([^:：]{1,30})[:：]\s*(.*)$")
SEP = re.compile(r"^\s*<!--\s*=+\s*-->\s*$")
ONE = re.compile(r"^\s*<!--\s*(.*?)\s*-->\s*$")


def v3_sections(text):
    """v3 の aboutme.md などを、区切りのコメントで欄に分ける。コメントは外す。"""
    lines = text.splitlines()
    out = [[None, []]]
    in_c = False
    comments = 0
    i = 0
    while i < len(lines):
        if (not in_c and SEP.match(lines[i]) and i + 2 < len(lines)
                and ONE.match(lines[i + 1]) and SEP.match(lines[i + 2])):
            out.append([ONE.match(lines[i + 1]).group(1), []])
            i += 3
            continue
        s, res = lines[i], ""
        had_comment = in_c or "<!--" in s
        while s:
            if in_c:
                j = s.find("-->")
                if j < 0:
                    s = ""
                    break
                s, in_c = s[j + 3:], False
            else:
                j = s.find("<!--")
                if j < 0:
                    res += s
                    break
                res, s, in_c = res + s[:j], s[j + 4:], True
        if had_comment and not SEP.match(lines[i]):
            comments += 1
        if res.strip():
            out[-1][1].append(res.rstrip())
        i += 1
    return [(t, ls) for t, ls in out if ls], comments


def items_of(lines):
    """箇条書きを「1つの項目 = 行頭の行 + 続きの行」に分ける。"""
    items = []
    for line in lines:
        m = BULLET.match(line)
        ind = len(line) - len(line.lstrip())
        if not m and items and items[-1][0] is not None and ind > items[-1][0]:
            items[-1][1].append(line)
            continue
        items.append([len(m.group(1)) if m else None, [line]])
    return items


def mark_items(lines, date, pre="", behavior=False):
    """項目の最後の行に〔v3 日付〕を付ける。子の項目を持つ見出しだけの行（「- 道具:」）には付けない。"""
    items = items_of(lines)
    out = []
    for n, (ind, ls) in enumerate(items):
        ls = list(ls)
        if ind is None:
            s = ls[0]
            if behavior and not s.lstrip().startswith((">", "|", "#")) and len(s) == len(s.lstrip()):
                ls[0] = f"- {pre}{s.strip()}"
                ls[-1] += f" 〔v3 {date}〕"
            out.append(ls)
            continue
        nxt = items[n + 1] if n + 1 < len(items) else None
        header = (len(ls) == 1 and re.search(r"[:：]\s*$", ls[0])
                  and nxt is not None and nxt[0] is not None and nxt[0] > ind)
        if pre and ind == 0:
            m = BULLET.match(ls[0])
            ls[0] = f"{m.group(1)}{m.group(2)} {pre}{m.group(3)}"
        if not header:
            ls[-1] += f" 〔v3 {date}〕"
        out.append(ls)
    return out


def drop_placeholders(lines):
    """「- 名前:」のように中身が空の行（子の行も無いもの）を外す。"""
    keep = []
    for i, line in enumerate(lines):
        m = BULLET.match(line)
        if m and re.match(r"^[^:：]+[:：]\s*$", m.group(3)):
            ind = len(m.group(1))
            child = False
            for nxt in lines[i + 1:]:
                if not nxt.strip():
                    continue
                child = (len(nxt) - len(nxt.lstrip())) > ind
                break
            if not child:
                continue
        keep.append(line)
    return keep


# ---------- 計画を作る ----------

class Plan:
    def __init__(self, v3, ws):
        self.v3, self.ws = v3, ws
        self.writes = {}        # ワークスペースの相対パス -> bytes（新しく作るもの）
        self.modifies = {}      # ワークスペースの相対パス -> (元の bytes, 新しい bytes)
        self.ledger = []        # (v3 の相対パス, 行き先, 理由)
        self.read = {}          # v3 の相対パス -> sha（読んだもの）
        self.secrets = []       # (v3 の相対パス, 行番号の一覧 or None)
        self.ask = []           # 本人に確かめること
        self.notes = []         # 知識の一覧の行
        self.projects = []      # (id, title, v3 の場所, 最後の記録)
        self.recipes = []       # 一覧の行
        self.counts = {}
        self.profile_added = []
        self.behavior_added = []
        self.behavior_default = []
        self.dupes = []
        self.conflicts = []     # (v3 の行, ワークスペースの行)
        self.unknown = []
        self.comment_lines = {}
        self.modes = {}         # ワークスペースの相対パス -> 元の権限（実行できるファイルなど）
        self.src_of = {}        # ワークスペースの相対パス -> v3 の相対パス（リンクを直すため）
        self.keeps = {}
        self.keep_layouts = {}
        self.recipe_units = {}
        self.recipe_files = []

    def count(self, k, n=1):
        self.counts[k] = self.counts.get(k, 0) + n

    def rel(self, p):
        return p.relative_to(self.v3).as_posix()

    def link(self, p):
        """v3 のファイルがリンクなら読まずに記録して True。"""
        if p.is_symlink():
            LINKS.append(p)
            return True
        return False

    def load(self, p):
        if p.is_symlink():
            raise Stop(f"v3 の中のリンクを読もうとしました（止めました）: {self.rel(p)}")
        info = p.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Stop("移行元のhardlinkまたは特殊ファイルは読みません。", 4)
        data = p.read_bytes()
        self.read[self.rel(p)] = sha(data)
        return data

    def load_text(self, p):
        """読んで、秘密らしい行を外した本文を返す。外した行は記録する。"""
        text, hits = redact(self.load(p).decode("utf-8", "replace"))
        if hits:
            self.secrets.append((self.rel(p), hits))
        return text

    def new(self, dest, data, src=None, why="", mode=None):
        if isinstance(data, str):
            data = data.encode("utf-8")
        safe_dest(self.ws, self.v3, dest)
        if os.path.lexists(self.ws / dest) or dest in self.writes:
            raise Stop(f"ワークスペースに同じ名前のファイルがあります: {dest}")
        self.writes[dest] = data
        if mode is not None:
            self.modes[dest] = mode
        if src:
            self.ledger.append((src, dest, why))
            self.src_of[dest] = src

    def archive(self, p, why):
        """元の写しを置く。文字のファイルは秘密らしい行だけ外す。"""
        rel = self.rel(p)
        data = self.load(p)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        if text is not None:
            text, hits = redact(text)
            if hits:
                self.secrets.append((rel, hits))
                why += "（秘密らしい行は外した）"
            data = text.encode("utf-8")
        self.new(f"imports/v3/{rel}", data, rel, why, mode=p.stat().st_mode & 0o777)
        self.count("archive")


def check_v3(v3):
    if not (v3 / "builder.md").is_file():
        raise Stop(f"v3 のフォルダではないようです（builder.md がありません）: {v3}")
    ver = (v3 / "VERSION").read_text(encoding="utf-8").strip() if (v3 / "VERSION").is_file() else "不明"
    warn = None
    if not ver.startswith("3."):
        warn = f"版が {ver} です。v3 の形のものだけを移します（v4 の試作のものは移しません）。"
    return ver, warn


def check_ws(ws, allow_migrated=False):
    for f in ["AGENTS.md", "wiki/index.md", "wiki/me/profile.md"]:
        if not (ws / f).is_file():
            raise Stop(f"ワークスペースではないようです（{f} がありません）: {ws}")
    if not allow_migrated and (ws / "wiki/notes/v3-migration.md").exists():
        raise Stop("このワークスペースには、もう v3 から移した記録があります（wiki/notes/v3-migration.md）。"
                   "2回は移しません。", 3)


def plan_profile(P):
    """aboutme.md と ai-behavior.md を、wiki/me/profile.md の欄に足す。"""
    path = "wiki/me/profile.md"
    safe_dest(P.ws, P.v3, path)
    orig = (P.ws / path).read_bytes()
    lines = orig.decode("utf-8").split("\n")
    existing = {norm(l) for l in lines if norm(l)}
    kv = {}     # ワークスペースの profile の「項目: 値」（食い違いを見つけるため）
    for l in lines:
        m = KV.match(norm(l))
        if m and BULLET.match(l) and m.group(2).strip():
            kv.setdefault(m.group(1).strip(), l.strip())
    adds = {}   # 欄の名前 -> 行

    def put(section, item, shown, check_kv=False):
        """項目（続きの行を含む）を足す。同じ項目がワークスペースにあれば足さない。
        同じ「項目:」で値が違えば profile に足さず、確認待ちに回す。"""
        n = norm(" ".join(l.strip() for l in item))
        if n and BULLET.match(item[0]) and n in existing:
            P.dupes.append(" ".join(l.strip() for l in item))
            return 0
        m = KV.match(norm(item[0])) if check_kv and BULLET.match(item[0]) else None
        if m and m.group(2).strip() and m.group(1).strip() in kv:
            P.conflicts.append((" ".join(l.strip() for l in item), kv[m.group(1).strip()]))
            return 0
        if n:
            existing.add(n)
        adds.setdefault(section, []).extend(item)
        shown.append(" ".join(l.strip() for l in item))
        return len(item)

    defaults = {norm(d) for d in V3_DEFAULT_BEHAVIOR}
    for name in ["aboutme.md", "ai-behavior.md"]:
        p = P.v3 / name
        if not p.is_file():
            continue
        if P.link(p):
            continue
        text = P.load_text(p)
        date = mdate(p)
        secs, ncomment = v3_sections(text)
        P.comment_lines[name] = ncomment
        P.archive(p, "元の写し（コメントも含めて元のまま）")
        moved = 0
        for title, body in secs:
            body = drop_placeholders(body)
            if name == "aboutme.md":
                t = re.sub(r"^\d+\.\s*", "", title or "")
                if "基本" in t:
                    sec = "基本"
                elif "仕事" in t:
                    sec = "仕事"
                elif "技術" in t or "スタック" in t:
                    sec = "使う道具・技術"
                elif "目標" in t or "目指" in t:
                    sec = "目指していること"
                else:
                    sec = f"{t}（v3 から）" if t else "そのほか（v3 から）"
                for item in mark_items(body, date):
                    moved += put(sec, item, P.profile_added, check_kv=True)
            else:
                t = title or ""
                if "絶対" in t:
                    pre = "【絶対】"
                elif "やってほしくない" in t or "しないで" in t:
                    pre = "【しないで】"
                elif "お願い" in t or "その他" in t or not t:
                    pre = ""
                elif "ドメイン" in t:
                    pre = "【ドメイン知識】"
                else:
                    pre = f"【{t}】"
                kept, skip_ind, parent = [], None, ""
                for ind, ls in items_of(body):
                    cur = ind if ind is not None else len(ls[0]) - len(ls[0].lstrip())
                    if skip_ind is not None and cur <= skip_ind:
                        skip_ind = None
                    joined = " ".join(l.strip() for l in ls)
                    if norm(joined) in defaults or all(norm(l) in defaults for l in ls):
                        P.behavior_default.append(joined)
                        if ind is not None and skip_ind is None:
                            skip_ind, parent = ind, norm(ls[0])
                        continue
                    if skip_ind is not None:
                        # 初期設定の項目の下に本人が書き足したもの: 親を付けて、いちばん上の項目にする
                        kept.append(f"- {norm(joined)}（v3 の初期設定「{parent[:30]}」の下に書いてあった）")
                        continue
                    kept += ls
                for item in mark_items(kept, date, pre, behavior=True):
                    moved += put("AIへのお願い", item, P.behavior_added)
                    if V3_WORDS.search(" ".join(item)):
                        P.ask.append(f"AI へのお願い「{norm(' '.join(l.strip() for l in item))}」は v3 の仕組みの言葉を含みます。"
                                     "OS でもこのまま守るか、言い換えるか。")
        P.ledger.append((name, path if moved else "（移す行なし）",
                         f"{moved} 行を profile.md の欄へ（〔v3 {date}〕付き）。コメント {ncomment} 行は元の写しにだけ残る"))

    if not adds:
        return
    order = ["基本", "仕事", "使う道具・技術", "得意・苦手", "目指していること", "AIへのお願い"]
    for sec in sorted(adds, key=lambda s: order.index(s) if s in order else len(order)):
        new_lines = adds[sec]
        head = f"## {sec}"
        if head in lines:
            i = lines.index(head) + 1
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            j = i
            while j > 0 and not lines[j - 1].strip():
                j -= 1
            lines[j:j] = new_lines
        else:
            before = None
            if sec == "使う道具・技術":
                before = next((h for h in ["## 得意・苦手", "## 目指していること", "## AIへのお願い"] if h in lines), None)
            if before is None and "## 変更の記録" in lines:
                before = "## 変更の記録"
            block = [head, ""] + new_lines + [""]
            if before:
                k = lines.index(before)
                lines[k:k] = block
            else:
                if lines and lines[-1].strip():
                    lines.append("")
                lines.extend(block)
    new = "\n".join(lines)
    new = re.sub(r"([^\n])\n(## )", r"\1\n\n\2", new)
    P.modifies[path] = (orig, new.encode("utf-8"))
    P.count("profile_lines", len(P.profile_added))
    P.count("behavior_lines", len(P.behavior_added))


def plan_knowledge(P):
    for name, title in [("domain-knowledge.md", "ドメイン知識"), ("design-knowledge.md", "デザインの好み")]:
        p = P.v3 / name
        if not p.is_file() or P.link(p):
            continue
        text = P.load_text(p)
        secs, _ = v3_sections(text)
        body = []
        for t, ls in secs:
            if t and not re.search(r"\.md\s*—|ドメイン知識\s*$|デザイン知識\s*$", t):
                body += ["", f"## {t}", ""]
            body += ls
        P.archive(p, "元の写し")
        if any(source == name for source, _ in P.secrets):
            continue
        if not "".join(body).strip():
            P.ledger.append((name, "（移さない）", "中身が空（ひな形のまま）"))
            continue
        dest = f"wiki/notes/v3/{name}"
        fm = ["---", f"title: {title}（v3 から）", "status: draft", f"updated: {mdate(p)}", f"source: v3 {name}", "---"]
        P.new(dest, "\n".join(fm + body).strip() + "\n", name, "コメントを外してノートに")
        P.notes.append(("本人の知識", f"- [{title}（v3 から）]({name})"))
        P.count("notes")

    kdir = P.v3 / "knowledge"
    if kdir.is_dir():
        for p in walk(kdir):
            rel = P.rel(p)
            if p.name == "README.md" or p.suffix != ".md":
                P.ledger.append((rel, "（移さない）", "v3 の説明のファイル"))
                continue
            text = P.load_text(p)
            if any(source == rel for source, _ in P.secrets):
                P.archive(p, "秘密らしい行を除いた写しだけ。通常の知識には入れない")
                continue
            t = first_h1(text.splitlines()) or p.stem
            dest = f"wiki/notes/v3/stack-knowledge/{p.name}"
            fm = ["---", f"title: {yq(t)}", "status: draft", f"updated: {mdate(p)}", f"source: v3 {rel}", "---", ""]
            P.new(dest, "\n".join(fm) + text, rel, "スタックの知識（本文は元のまま）")
            P.notes.append(("スタックの知識", f"- [{t}](stack-knowledge/{p.name})"))
            P.count("notes")


def plan_wiki(P):
    w = P.v3 / "wiki"
    cards_by_project = {}
    project_cards = {}
    if not w.is_dir():
        return cards_by_project, project_cards
    for p in walk(w):
        rel = P.rel(p)
        parts = Path(rel).parts           # ("wiki", 種類, ...)
        top = parts[1] if len(parts) > 1 else ""
        if top == "me":
            P.ledger.append((rel, "（移さない）", "v4 の試作の「私について」。今回の対象外"))
            P.count("v4")
            continue
        if top in WIKI_SYSTEM:
            P.ledger.append((rel, "（移さない）", "v3 の Wiki の仕組み・自動で作られる一覧"))
            P.count("system")
            continue
        if is_secret_name(p.name):
            P.secrets.append((rel, None))
            P.ledger.append((rel, "（移さない）", "秘密のファイルの名前"))
            continue
        if top in WIKI_ARCHIVE:
            P.archive(p, "日付の索引・操作の記録など。知識には変えず、元の写しだけ")
            continue
        text = P.load_text(p) if p.suffix == ".md" else read_text(p)
        if p.suffix == ".md" and any(source == rel for source, _ in P.secrets):
            P.archive(p, "秘密らしい行を除いた写しだけ。通常の知識には入れない")
            continue
        if p.suffix != ".md" and text is not None and secret_lines(P.load(p).decode("utf-8")):
            P.secrets.append((rel, secret_lines(text)))
            P.ledger.append((rel, "（移さない）", "秘密らしい文字列がある"))
            continue
        if top == "projects" and p.suffix == ".md" and len(parts) == 3:
            fm, body = split_fm(text)
            k = fm_keys(fm)
            pid = k.get("id") or p.stem
            project_cards[pid] = (rel, k, fm or [], body, p)
            base = Path(k.get("path", "")).name
            if base and base != pid:
                project_cards[base] = project_cards[pid]
            continue
        if top in CARD_DIRS and p.suffix == ".md" and text is not None:
            v3_topics.assignments(text.encode(), rel)
            fm, body = split_fm(text)
            k = fm_keys(fm)
            st = k.get("status", "")
            if st in ("unverified", "outdated"):
                P.archive(p, f"v3 で「{st}」（参照しない印）。知識には入れず、元の写しだけ")
                continue
            title = k.get("title") or first_h1(body) or p.stem
            new_fm, seen = [], False
            for line in fm or []:
                m = re.match(r"^status:\s*(.*)$", line)
                if m and not seen:
                    new_fm += ["status: draft", f"v3_status: {m.group(1).strip()}"]
                    seen = True
                elif re.match(r"^source:", line):
                    new_fm.append("v3_" + line)
                else:
                    new_fm.append(line)
            if "title" not in k:
                new_fm.insert(0, f"title: {yq(title)}")
            if not seen:
                new_fm.append("status: draft")
            if "updated" not in k:
                new_fm.append(f"updated: {mdate(p)}")
            new_fm.append(f"source: v3 {rel}")
            dest = "wiki/notes/v3/" + "/".join(parts[1:])
            P.new(dest, "---\n" + "\n".join(new_fm) + "\n---\n" + "\n".join(body), rel,
                  "知識のカード（v3 の項目は全部残し、status を draft に）")
            star = " ★" if k.get("important") == "true" else ""
            summ = f" — {k['summary']}" if k.get("summary") else ""
            P.notes.append((top, f"- [{title}]({'/'.join(parts[1:])}){star}{summ}"))
            P.count("cards")
            if k.get("project"):
                cards_by_project.setdefault(k["project"], []).append((top, title, "/".join(parts[1:])))
            continue
        if text is not None:
            P.archive(p, "v3 の Wiki の、種類の分からないファイル。元の写しだけ")
            P.unknown.append(rel)
        else:
            P.ledger.append((rel, "（移さない）", "文字ではないファイル"))
    return cards_by_project, project_cards


def latest_record(d):
    best = None
    for sub in [".project-memory/revisions", ".claude/.tmp/revisions"]:
        r = d / sub
        if r.is_dir():
            for p in walk(r):
                m = re.match(r"^(\d{4}-\d{2}-\d{2})", p.name)
                if m and (best is None or p.name > best[1].name):
                    best = (m.group(1), p)
    return best


def readme_lead(lines):
    out, started = [], False
    for line in lines:
        s = line.strip()
        if s.startswith("#") or s.startswith("<!--") or s.startswith("```") or s.startswith("|") or s.startswith("!["):
            if started:
                break
            continue
        if not s:
            if started:
                break
            continue
        out.append(s)
        started = True
    lead = " ".join(out)
    return (lead[:300] + "…") if len(lead) > 300 else lead


class DashboardText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []
        self.data = []
        self.dashboard_data = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        if tag == "script" and dict(attrs).get("id") == "dashboard-data":
            self.dashboard_data = True
        if not self.hidden and tag in {"h1", "h2", "h3", "h4", "p", "div", "section", "tr", "li", "br"}:
            self.parts.append("\n\n" if tag.startswith("h") else "\n")
        if not self.hidden and tag in {"td", "th"}:
            self.parts.append(" / ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "script":
            self.dashboard_data = False

    def handle_data(self, data):
        if self.dashboard_data:
            self.data.append(data)
        elif not self.hidden:
            self.parts.append(data)


def project_documents(P, directory, destination):
    sections = []
    dashboard = directory / "dashboard.html"
    if dashboard.is_file() and not P.link(dashboard):
        parser = DashboardText()
        parser.feed(P.load_text(dashboard))
        sections += ["### v3 のダッシュボード", "", "移行時点の記録です。提案・件数・動作状況は現在の確認結果ではありません。", ""]
        try:
            data = json.loads("".join(parser.data)) if parser.data else None
        except (ValueError, TypeError):
            data = None
        if isinstance(data, dict):
            def literal(value):
                return str(value).replace("\n", " ").replace("\r", " ").replace("|", "｜")

            project = data.get("project")
            if isinstance(project, dict):
                sections += ["### 案件の情報（移行時点）", "", "| 項目 | 内容 |", "| --- | --- |"]
                sections += [f"| {literal(key)} | {literal(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value)} |"
                             for key, value in project.items()]
                sections.append("")
            for field, heading, columns in (
                ("proposals", "今のあなたへの提案", (("title", "提案"), ("desc", "内容"), ("say", "話しかけ方"))),
                ("catalog", "できること（話しかけるだけ）", (("want", "困りごと・やりたいこと"), ("say", "AIへの言い方"))),
                ("linked", "関連する案件", (("name", "案件"), ("desc", "内容"), ("say", "話しかけ方"), ("freq", "頻度"), ("place", "場所"))),
                ("activity", "最近の動き", (("date", "日付"), ("text", "内容"))),
            ):
                rows = data.get(field, [])
                if isinstance(rows, list) and rows:
                    sections += [f"### {heading}", "", "| " + " | ".join(label for _, label in columns) + " |",
                                 "| " + " | ".join("---" for _ in columns) + " |"]
                    sections += ["| " + " | ".join(literal(row.get(key, "")) for key, _ in columns) + " |"
                                 for row in rows if isinstance(row, dict)]
                    sections.append("")
            sections += ["### ダッシュボードの全データ（移行時点）", "", "````json",
                         json.dumps(data, ensure_ascii=False, indent=2).replace("`", "\\u0060"), "````", ""]
            if "".join(parser.parts).strip():
                sections += ["### 旧画面の補足（静的テキスト）", "", "````text",
                             "".join(parser.parts).strip().replace("`", "ˋ"), "````", ""]
        else:
            sections += ["### 旧画面のテキスト（要確認）", "", "````text",
                         "".join(parser.parts).strip().replace("`", "ˋ"), "````", ""]
            P.ask.append(f"{P.rel(dashboard)} は定型データを読めませんでした。画面のテキストのみ移行。動的情報は元画面と照合してください。")
        P.ledger.append((P.rel(dashboard), destination, "HTML/JavaScriptは実行せずダッシュボードの情報だけを移行"))
    readme = directory / "README.md"
    sections += ["## README", ""]
    if readme.is_file() and not P.link(readme):
        sections += ["v3 の説明書を移行時点の記録として保持。相対リンクは元の案件フォルダ基準です。再開時に照合して更新してください。", "",
                     P.load_text(readme), ""]
        P.ledger.append((P.rel(readme), destination, "READMEは要約だけでなく本文を保持"))
    else:
        sections += ["旧READMEはありません。再開時に使い方・試験・復旧方法を確認します。", ""]
    return sections


def plan_projects(P, cards_by_project, project_cards):
    out = P.v3 / "output"
    names = []
    if out.is_dir():
        for d in sorted(out.iterdir()):
            if d.is_dir() and not d.name.startswith(("_", ".")):
                names.append(d.name)
            elif d.is_dir():
                P.ledger.append((f"output/{d.name}/", "（移さない）", "v3 の控え・下見のフォルダ"))
    for pid, card in project_cards.items():
        base = Path(card[1].get("path", "")).name
        if card[4].stem == pid and pid not in names and base not in names:
            names.append(pid)
    for name in names:
        d = out / name
        card = project_cards.get(name)
        oid = slug(name)
        dest = f"wiki/projects/{oid}.md"
        if oid == "index" or (P.ws / dest).exists():
            dest = f"wiki/projects/{oid}-v3.md"
            P.ask.append(f"ワークスペースに同じ名前の仕事「{oid}」があります。v3 のほうは {dest} に分けました。同じ仕事なら、まとめてよいか。")
        page = Path(dest).stem      # 写す先 projects/<page>/ はページの名前にそろえる
        title, lead, date, rec = name, "", None, None
        if (d / "README.md").is_file() and not P.link(d / "README.md"):
            rl = P.load_text(d / "README.md").splitlines()
            title = first_h1(rl) or name
            lead = readme_lead(rl)
            date = mdate(d / "README.md")
        if d.is_dir():
            lr = latest_record(d)
            if lr:
                date, rec = lr[0], lr[1].relative_to(d).as_posix()
                P.load(lr[1])
                if secret_lines(rec):
                    rec = "（名前に秘密らしい文字列があるので書かない）"
        if card:
            ck = card[1]
            title = ck.get("title") or title
            lead = lead or ck.get("summary", "")
            date = date or ck.get("updated")
        date = date or TODAY
        has_code = d.is_dir()
        body = ["---", f"title: {yq(title)}", "status: paused", f"updated: {date}"]
        if has_code:
            body.append(f"v3_path: {yq('output/' + name + '/')}")
        body += ["next: " + (f"続けるなら、写してよいかを本人に聞いてから、v3 の output/{name}/ をワークスペースの projects/{page}/ に写す（tools/v3-migration.md）"
                             if has_code else "続けるかどうかを本人に聞く"),
                 "---", "## ダッシュボード", "", "### 目的"]
        body.append(f"- {lead}（v3 の README より。未確認）" if lead else "- （v3 に書かれていない）")
        body += ["", "### 完成の条件", "- （v3 から移した。まだ聞いていない）", "", "### いまの状況",
                 f"- {TODAY} に kote2 Builder v3 から移した。まだ再開していない"]
        if has_code:
            body.append(f"- 成果物（コード）は v3 の `output/{name}/` にあり、ワークスペースにはまだ写していない。写す先は `projects/{page}/`（v3 の場所は [移行の記録](../notes/v3-migration.md)）")
        if rec:
            body.append(f"- v3 の最後の作業記録: `output/{name}/{rec}`（{date}）")
        body += ["", "### 未決", "- 続けるかどうか", "", "### 決定ログ", ""]
        rel_cards = cards_by_project.get(name, []) + (cards_by_project.get(card[1].get("id"), []) if card else [])
        if rel_cards:
            body += ["## v3 の関係する記録"]
            seen = set()
            for top, t, path in rel_cards:
                if path not in seen:
                    seen.add(path)
                    body.append(f"- [{t}](../notes/v3/{path})（{top}）")
            body.append("")
        if card:
            rel, ck, fm, cbody, _ = card
            body += ["## v3 の紹介カード（元のまま）", ""]
            for line in fm:
                if re.match(r"^[A-Za-z_]", line) and not re.match(r"^(title|id):", line):
                    body.append(f"- v3 の {line}")
            body.append("")
            body += [("##" + l if l.startswith("#") else l) for l in cbody]
            P.ledger.append((rel, dest, "仕事の紹介カード（本文は案件ページの末尾に元のまま）"))
        body += project_documents(P, d, dest)
        P.new(dest, "\n".join(body).rstrip() + "\n",
              f"output/{name}/" if has_code else None, "仕事のページ（コードは写していない）")
        P.projects.append((oid, title, f"output/{name}/" if has_code else "（コードなし）", rec or "", dest))
        P.count("projects")


RECIPE_ASIDE = "recipes/from-v3/"


def recipe_dest(P, rel):
    """v3 のレシピの相対パス → ワークスペースでの場所（名前が重なり別の場所へ置いたものを読み替える）。"""
    for unit, dest in P.recipe_units.items():
        if rel == unit or rel.startswith(unit + "/"):
            return dest + rel[len(unit):]
    return rel


def recipe_existing(P, dest, data, mode):
    """ワークスペースの同じ場所: 無ければ None、同じ中身と実行の印なら True、違えば False（どちらも書き換えない）。"""
    safe_dest(P.ws, P.v3, dest)
    path = P.ws / dest
    if not os.path.lexists(path):
        return None
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        return False
    return path.read_bytes() == data and bool(info.st_mode & 0o111) == bool(mode & 0o111)


def keep_mark(data, mode):
    return sha(data) + (":x" if mode & 0o111 else ":-")


def recipe_layout(root):
    if not root.is_dir() or root.is_symlink():
        return None
    entries = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            kind = stat.S_IFMT(path.lstat().st_mode)
            entries[path.relative_to(root).as_posix()] = kind
            if kind == stat.S_IFDIR:
                pending.append(path)
    return entries


def plan_recipes(P):
    r = P.v3 / "recipes"
    if not r.is_dir():
        return
    v2_dirs = {p.parent for p in r.rglob("recipe.json") if not set(p.parts) & SKIP_DIRS}
    units = {}
    for p in walk(r):
        rel = P.rel(p)
        if p.parent == r and p.name == "README.md":
            P.ledger.append((rel, "（移さない）", "v3 のレシピの説明。OS では wiki/notes/v3/recipes.md"))
            continue
        if is_secret_name(p.name):
            P.secrets.append((rel, None))
            P.ledger.append((rel, "（移さない）", "秘密のファイルの名前"))
            continue
        data = P.load(p)
        text = read_text(p)
        if text is not None and secret_lines(text):
            P.secrets.append((rel, secret_lines(text)))
            P.ledger.append((rel, "（移さない）", "秘密らしい文字列がある"))
            continue
        unit = ([d for d in p.parents if d in v2_dirs] or [p])[-1]
        units.setdefault(unit, []).append((rel, data, p.stat().st_mode & 0o777))
    for unit, items in units.items():
        urel = P.rel(unit)
        states = [recipe_existing(P, rel, data, mode) for rel, data, mode in items]
        layout = None
        same_layout = True
        if unit.is_dir():
            safe_dest(P.ws, P.v3, urel)
            layout = recipe_layout(P.ws / urel)
            same_layout = layout == recipe_layout(unit)
        if all(s is None for s in states) and not layout:
            for rel, data, mode in items:
                P.new(rel, data, rel, "レシピ（形を変えずに）", mode=mode)
                P.recipe_files.append((rel, rel, data))
                P.count("recipe_files")
        elif all(states) and same_layout:
            P.recipe_units[urel] = urel
            if layout is not None:
                P.keep_layouts[urel] = layout
            for rel, data, mode in items:
                P.keeps[rel] = keep_mark(data, mode)
                P.ledger.append((rel, rel, "レシピ（ワークスペースに同じものがあるので書かない）"))
                P.recipe_files.append((rel, rel, data))
                P.count("recipe_files")
            P.count("recipe_same")
        else:
            dest = RECIPE_ASIDE + urel[len("recipes/"):]
            P.recipe_units[urel] = dest
            for rel, data, mode in items:
                P.new(recipe_dest(P, rel), data, rel, "レシピ（ワークスペースに同じ名前の別の版があるので別の場所へ。どちらも書き換えない）", mode=mode)
                P.recipe_files.append((rel, recipe_dest(P, rel), data))
                P.count("recipe_files")
            P.count("recipe_aside")
            P.ask.append(f"レシピ `{urel}` はワークスペースに同じ名前で中身の違うものがあった。ワークスペースのものは変えず、v3 の版を `{dest}` に置いた。"
                         "どちらを使うか（名前が重なるので、使わないほうの扱いを本人と決める）")
    for d in sorted(v2_dirs):
        rel = P.rel(d)
        excluded = {s for s, _ in P.secrets}
        j = {}
        if f"{rel}/recipe.json" not in excluded and not (d / "recipe.json").is_symlink():
            try:
                j = json.loads((d / "recipe.json").read_text(encoding="utf-8"))
            except Exception:
                j = {}
        texts = "".join((read_text(f) or "") for f in walk(d) if f.suffix == ".md")
        flag = " 【v3 の道具の手順あり】" if V3_TOOL_STEP.search(texts) else ""
        flag += recipe_flag(P, rel)
        P.recipes.append(f"- [{j.get('name', d.name)}](../../../{recipe_dest(P, rel)}/RECIPE.md)（{d.name}・パッケージ・{j.get('status', '?')}）{flag} — {j.get('summary', '')}")
        P.count("recipes")
    for p in walk(r):
        if p.suffix != ".md" or p.name == "README.md" or any(v in p.parents for v in v2_dirs):
            continue
        rel = P.rel(p)
        if any(rel == s for s, _ in P.secrets):
            continue
        lines = redact(read_text(p) or "")[0].splitlines()
        t = first_h1(lines) or p.stem
        flag = " 【v3 の道具の手順あり】" if V3_TOOL_STEP.search("\n".join(lines)) else ""
        flag += recipe_flag(P, rel)
        P.recipes.append(f"- [{t}](../../../{recipe_dest(P, rel)})（{p.stem}・1ファイル）{flag} — {readme_lead(lines)[:120]}")
        P.count("recipes")


def recipe_flag(P, rel):
    dest = P.recipe_units.get(rel)
    if dest is None:
        return ""
    return " 【ワークスペースに同じものあり】" if dest == rel else " 【ワークスペースに同じ名前の別の版あり・v3 の版は from-v3 に置いた】"


RECIPE_LINKS = "wiki/notes/v3/recipe-links.md"
MD_REF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>\r\n]*>|\S+)", re.M)
RECIPE_MD_LINK = re.compile(r"\]\(\s*(<[^>\r\n]*>|[^)\r\n]*)\)")


def plan_recipe_links(P):
    """レシピを別の場所へ置いたとき、レシピの本文は変えずに、相対リンクの元 → 先の対応表と未解決を案内に残す。"""
    import posixpath
    if not P.counts.get("recipe_aside"):
        return
    aside = [d for u, d in P.recipe_units.items() if u != d]
    fixes, unresolved = [], []
    for src, dest, data in P.recipe_files:
        if not src.endswith(".md"):
            continue
        moved_file = any(dest == a or dest.startswith(a + "/") for a in aside)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            unresolved.append((dest, "（本文）", "UTF-8 として読めないので調べていない"))
            continue
        targets = [re.sub(r'\s+"[^"]*"\s*$', '', m.group(1)).strip() for m in RECIPE_MD_LINK.finditer(text)] + MD_REF.findall(text)
        for target in targets:
            bare = target[1:-1] if target.startswith("<") and target.endswith(">") else target
            if re.match(r"^[a-z][a-z0-9+.-]*:", bare, re.I) or bare.startswith(("#", "/")):
                continue
            if target.startswith("<") or re.search(r"\s|\(", target):
                unresolved.append((dest, target, "書き方を解析できない"))
                continue
            raw_path = target.split("#", 1)[0].split("?", 1)[0]
            try:
                if re.search(r"%(?![0-9a-fA-F]{2})", raw_path):
                    raise ValueError
                path = unquote(raw_path, errors="strict")
            except (UnicodeDecodeError, ValueError):
                unresolved.append((dest, target, "書き方を解析できない"))
                continue
            if re.match(r"^[a-z][a-z0-9+.-]*:", path, re.I) or path.startswith(("/", "\\")):
                continue
            if not path:
                continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(src), path))
            current = posixpath.normpath(posixpath.join(posixpath.dirname(dest), path))
            to = None if resolved.startswith("..") else map_v3_path(resolved, P)
            if to:
                if to != current:
                    new = posixpath.relpath(to, posixpath.dirname(dest)) + ("/" if path.endswith("/") else "")
                    fixes.append((dest, target, quote(new, safe="/.-_~") + target[len(raw_path):], src))
                continue
            if moved_file and not (current in P.writes or current in P.keeps or os.path.lexists(P.ws / current)):
                why = ("v3 の外を指す" if resolved.startswith("..") else
                       "v3 にはあるがワークスペースへ移していない" if os.path.lexists(P.v3 / resolved) else "v3 にも見つからない")
                unresolved.append((dest, target, why))
    fixes, unresolved = list(dict.fromkeys(fixes)), list(dict.fromkeys(unresolved))
    cell = lambda s: "`" + s.replace("|", "\\|").replace("`", "'") + "`"
    out = ["---", "title: 別の場所へ置いたレシピの参照案内（v3 から）", "status: draft", f"updated: {TODAY}", "source: v3 の recipes/", "---",
           f"ワークスペースに同じ名前で中身の違うレシピがあったので、v3 の版を `{RECIPE_ASIDE}` に置いた。レシピの本文・コードは v3 のまま変えていない。",
           "そのため本文の相対リンクには、ワークスペースでは別のものを指したり、何も指さなかったりするものがある。"
           "v3 の版のレシピ（とそれを指すレシピ）を使う前にこの表を読み、本文のリンクの代わりに「ワークスペースでの正しいリンク」を使う。",
           "元の場所は `imports/v3/ledger.md`、どちらの版を使うかは `wiki/notes/v3-migration.md` の「本人に確かめること」。",
           "調べたのは Markdown の `[..](..)`・`![..](..)`・参照の定義だけ。HTML の属性やコードの中のパス、Markdown 以外のファイルは調べていない。", "",
           f"## リンクの対応表（{len(fixes)}）", "",
           "| レシピ（ワークスペース） | 本文のリンク | ワークスペースでの正しいリンク | v3 の元 |", "|---|---|---|---|"]
    out += [f"| {cell(d)} | {cell(t)} | {cell(n)} | {cell(s)} |" for d, t, n, s in fixes] or ["| （なし） | | | |"]
    out += ["", f"## 未解決（{len(unresolved)}）", "",
            "先が見つからない・解析できないリンク。推測で直さず、使う前に本人に伝える。", "",
            "| レシピ（ワークスペース） | 本文のリンク | 理由 |", "|---|---|---|"]
    out += [f"| {cell(d)} | {cell(t)} | {w} |" for d, t, w in unresolved] or ["| （なし） | | |"]
    P.new(RECIPE_LINKS, "\n".join(out) + "\n")
    P.count("recipe_link_fixes", len(fixes))
    P.count("recipe_link_unresolved", len(unresolved))
    P.ask.append(f"別の場所へ置いたレシピがある。v3 の版のレシピを使う前に `{RECIPE_LINKS}` のリンクの対応表と未解決を読む"
                 f"（対応 {len(fixes)} 件・未解決 {len(unresolved)} 件。本文は変えていない）")


def plan_top(P):
    for p in sorted(P.v3.iterdir()):
        n = p.name
        if n in USER_FILES or n in ("knowledge", "recipes", "wiki", "output") or n in SKIP_FILES:
            continue
        if n in V3_SYSTEM_TOP:
            if n == ".claude":
                for sk in sorted((p / "skills").iterdir()) if (p / "skills").is_dir() else []:
                    if sk.is_dir():
                        P.ledger.append((f".claude/skills/{sk.name}/", "（移さない）", "スキル。使いたければ本人に聞いてから写す"))
                        P.ask.append(f"v3 にスキル「{sk.name}」があります（移していません）。OS でも使いたいか。")
                styles = p / "output-styles"
                if styles.is_dir():
                    for f in walk(styles):
                        P.archive(f, "口調の設定。元の写しだけ")
                        P.ask.append(f"v3 の口調の設定 {P.rel(f)} があります。OS の話し方に入れたいか。")
            P.ledger.append((n + ("/" if p.is_dir() else ""), "（移さない）", "v3 の仕組み"))
            P.count("system")
        elif n in V4_TOP:
            P.ledger.append((n + "/", "（移さない）", "v4 の試作のもの。今回の対象外"))
            P.count("v4")
        elif is_secret_name(n):
            P.secrets.append((n, None))
            P.ledger.append((n, "（移さない）", "秘密のファイルの名前"))
        elif n.endswith(".local.md") and p.is_file():
            text = read_text(p) or ""
            if secret_lines(text):
                P.secrets.append((n, secret_lines(text)))
                P.ledger.append((n, "（移さない）", "秘密らしい文字列がある"))
            else:
                P.archive(p, "本人の手元のメモ。元の写しだけ")
                P.ask.append(f"v3 に手元のメモ {n} があります。中身を Wiki に入れたいか。")
        else:
            P.ledger.append((n + ("/" if p.is_dir() else ""), "（移さない）", "v3 の標準には無いもの"))
            P.unknown.append(n + ("/" if p.is_dir() else ""))


def plan_pages(P, ver):
    # 知識の一覧
    groups = {}
    for g, line in P.notes:
        groups.setdefault(g, []).append(line)
    names = {"本人の知識": "本人の知識", "スタックの知識": "スタックの知識（v3 の knowledge/）",
             "knowledge": "知識", "troubleshooting": "トラブルと対処", "decisions": "決めたこと",
             "patterns": "よく効いた型", "sources": "資料の要約", "stacks": "技術の分類"}
    if P.notes:
        out = ["---", "title: v3 から移した知識の一覧", "status: draft", f"updated: {TODAY}",
               "source: v3 の wiki/・knowledge/・domain-knowledge.md など", "---",
               "v3 から移した知識です。どれも `status: draft`（未確認）。使うときは「v3 の記録では」と添えます。★ は v3 で大事の印が付いていたもの。", ""]
        for g in ["本人の知識", "knowledge", "troubleshooting", "decisions", "patterns", "sources", "stacks", "スタックの知識"]:
            if g in groups:
                out += [f"## {names[g]}（{len(groups[g])}）"] + groups[g] + [""]
        P.new("wiki/notes/v3/index.md", "\n".join(out))
    if P.recipes:
        out = ["---", "title: レシピの一覧（v3 から）", "status: draft", f"updated: {TODAY}", "source: v3 の recipes/", "---",
               "レシピはワークスペースの `recipes/` に、v3 の形のまま置いてあります。",
               "",
               "使い方: 「〜を作って」と言われたら、ここから合うレシピを探し、本文（パッケージは RECIPE.md）を読んで作る。"
               "成果物は `projects/<名前>/` に置く。手順はワークスペースの `tools/recipes.md` の「使う」と「v3 のレシピ」。",
               "【v3 の道具の手順あり】のレシピは、v3 の道具（`scripts/` や `builder.md` など）を使う手順をそのまま実行しない。"
               "`tools/recipes.md` の読み替えの表に従い、OS でどうするかを本人に伝えてから進める。", "",
               *([f"`{RECIPE_ASIDE}` に置いた v3 の版のレシピは、使う前に[参照案内](recipe-links.md)のリンクの対応表と未解決を読む。", ""]
                 if RECIPE_LINKS in P.writes else []),
               f"## レシピ（{len(P.recipes)}）"] + P.recipes + [""]
        P.new("wiki/notes/v3/recipes.md", "\n".join(out))


def plan_record(P, ver, warn):
    c = P.counts
    sec = []
    for rel, lines in P.secrets:
        sec.append(f"- `{rel}`" + (f"（{', '.join(map(str, lines[:10]))} 行目）" if lines else "（名前）"))
    out = ["---", "title: kote2 Builder v3 からの移行の記録", "status: confirmed", f"updated: {TODAY}", "---",
           f"- 移した日: {TODAY}（tools/migrate_v3.py）",
           f"- v3 の版: {ver}",
           f"- v3 の場所: `{P.v3}`（仕事のコードを写すときに使う。v3 は変えていない）",
           "", "## 結果",
           f"- プロフィール: {c.get('profile_lines', 0)} 行を `me/profile.md` の欄へ（〔v3 日付〕付き。日付は v3 のファイルの更新日。本人確認はまだ）",
           f"- AI へのお願い: {c.get('behavior_lines', 0)} 行を `me/profile.md` の「AIへのお願い」へ",
           f"- 知識: カード {c.get('cards', 0)} 枚・ノート {c.get('notes', 0)} 件" + (" → [一覧](v3/index.md)" if P.notes else ""),
           f"- 仕事: {c.get('projects', 0)} 件 → `projects/`（一時停止。コードは写していない）",
           f"- レシピ: {c.get('recipes', 0)} 件（{c.get('recipe_files', 0)} ファイル）→ ワークスペースの `recipes/`" + ("、[一覧](v3/recipes.md)" if P.recipes else ""),
           *([f"  - ワークスペースに同じものがあったので書かなかった: {c.get('recipe_same', 0)} 件・同じ名前で中身が違うので v3 の版を `{RECIPE_ASIDE}` に置いた: "
              f"{c.get('recipe_aside', 0)} 件（ワークスペースのものは変えていない）"] if c.get('recipe_same') or c.get('recipe_aside') else []),
           *([f"  - 別の場所へ置いたレシピの参照案内: [リンクの対応表と未解決](v3/recipe-links.md)（対応 {c.get('recipe_link_fixes', 0)} 件・"
              f"未解決 {c.get('recipe_link_unresolved', 0)} 件。レシピの本文は変えていない）"] if RECIPE_LINKS in P.writes else []),
          f"- 元の写しだけ: {c.get('archive', 0)} 件 → ワークスペースの `imports/v3/`（正本ではない。ふだん読まない）",
           f"- 1つずつの行き先: `imports/v3/ledger.md`",
           "", "## 本人に確かめること（1回に1つ）"]
    own = (P.ws / "wiki/me/profile.md").read_text(encoding="utf-8").split("\n")
    if any(BULLET.match(l) and "〔本人" in l for l in own):
        # ワークスペースに本人の行がある: 本人がもう話したことは聞き直さない
        out += ["- プロフィールの〔v3〕の行が、いまも正しいか（本人がもう話したこと（〔本人〕の行）は聞き直さない。食い違いと、いまの仕事に関わる行から）"]
    else:
        out += ["- プロフィールの〔v3〕の行が、いまも正しいか（まず呼び方）"]
    out += [f"- {a}" for a in dict.fromkeys(P.ask)]
    if P.conflicts:
        out += [f"- プロフィールと v3 で値が食い違う行 {len(P.conflicts)} 件（profile には足さず、`me/proposals.md` の確認待ちに入れた）。どちらが正しいか"]
    if P.dupes:
        out += [f"- ワークスペースに同じ行があったので足さなかった: {len(P.dupes)} 行（imports/v3/ledger.md）"]
    if LINKS:
        out += [f"- v3 の中にリンク（別の場所を指すもの）が {len(LINKS)} 個あった。先は読まず、移していない: "
                + "、".join(f"`{P.rel(l)}`" for l in LINKS[:10]) + ("ほか" if len(LINKS) > 10 else "")]
    if P.unknown:
        out += ["- v3 にあった、種類の分からないもの（移していない、または元の写しだけ）: " + "、".join(f"`{u}`" for u in P.unknown[:30])
                + ("ほか" if len(P.unknown) > 30 else "")]
    if warn:
        out += [f"- {warn}"]
    out += ["", "## 仕事（v3 の生成プロジェクト）",
            "コードは v3 に残っている（ワークスペースには写していない）。本人が「〇〇の続きをしたい」と言ったら、写してよいかを聞いてから写す（`tools/v3-migration.md`）。"
            "v3 のフォルダを消すと、写していないコードは無くなる。動かしたら、上の「v3 の場所」を新しい場所に直す。", "",
            "| 仕事 | ページ | v3 の場所 | 最後の作業記録 |", "|---|---|---|---|"]
    for oid, title, loc, rec, dest in P.projects:
        out.append(f"| {title.replace('|', '／')} | [{oid}](../{dest[len('wiki/'):]}) | `{loc}` | {rec} |")
    out += ["", "## 移さなかったもの",
            f"- v3 の初期設定のお願い（本人が書いたものではない）: {len(P.behavior_default)} 行"]
    out += [f"  - {b}" for b in P.behavior_default if b.startswith(("-", "*"))]
    out += [f"- v3 の仕組み（builder.md・hooks・templates・scripts・ダッシュボード・Wiki の画面など）: {c.get('system', 0)} 件",
            f"- v4 の試作のもの: {c.get('v4', 0)} 件",
            f"- 秘密として外したもの: {len(P.secrets)} 件（ファイルごと、または秘密らしい行だけ外した。中身は書いていない）"] + sec
    P.new("wiki/notes/v3-migration.md", "\n".join(out) + "\n")


def module_api():
    return sys.modules.get(__name__) or SimpleNamespace(**globals())


def plan_index(P):
    path = "wiki/index.md"
    api = module_api()
    data = v3_topics.planned_data(P, path, api)
    namespace = "os-wiki-navigation"
    outside = v3_topics.region(data, "", namespace).decode("utf-8")
    outside = re.sub(r"<!-- os-wiki-navigation:begin -->.*?<!-- os-wiki-navigation:end -->", "", outside, flags=re.S)
    entries = [("知識", "notes/index.md"), ("案件", "projects/index.md"),
               ("レシピ", "../tools/recipes.md"), ("読み書き・保存", "README.md")]
    destinations = v3_topics.markdown_destinations(outside)
    links = [v3_topics.entry_link(label, target) for label, target in entries
             if target not in destinations]
    if P.recipes and "notes/v3/recipes.md" not in destinations:
        recipe_heading = "## レシピ（ワークスペースの recipes/）"
        legacy_recipe_heading = "## レシピ（作業場の recipes/）"
        if not any(heading in outside.splitlines() for heading in (recipe_heading, legacy_recipe_heading)):
            links += ["", recipe_heading]
        links.append("- [v3 から移したレシピの一覧](notes/v3/recipes.md)")
    if links or "<!-- os-wiki-navigation:" in data.decode("utf-8"):
        v3_topics.put(P, path, v3_topics.region(data, "\n".join(links), namespace), api)


def plan_entries(P):
    api = module_api()
    v3_topics.notes_entry(P, api)
    path = "wiki/projects/index.md"
    data = v3_topics.planned_data(P, path, api, "# 案件の入口\n".encode())
    if secret_lines(data.decode("utf-8")):
        raise Stop("案件の索引に秘密らしい文字列があります。中身を計画へ写さず止めました。", 4)
    lines = ["## active", "", "## paused"]
    for _, title, _, _, destination in P.projects:
        lines.append(v3_topics.entry_link(title + "（paused）", Path(destination).name))
    lines += ["", "## done"]
    updated = v3_topics.region(data, "\n".join(lines), "os-migration-projects")
    if P.projects or not os.path.lexists(P.ws / path):
        v3_topics.put(P, path, updated, api)


def plan_proposals(P):
    """profile と値が食い違った v3 の行を、確認待ちに入れる（どちらも消さない）。"""
    if not P.conflicts:
        return
    path = "wiki/me/proposals.md"
    if not (P.ws / path).is_file():
        raise Stop("wiki/me/proposals.md がありません。食い違いの置き場が無いので止めました。")
    safe_dest(P.ws, P.v3, path)
    orig = (P.ws / path).read_bytes()
    lines = orig.decode("utf-8").split("\n")
    new = [f"- {TODAY} v3 と食い違い（出どころ: v3 の aboutme.md）: v3 では「{norm(v)}」、いまの profile では「{norm(e)}」。どちらが正しいか本人に聞く"
           for v, e in P.conflicts]
    head = "## 確認待ち"
    if head not in lines:
        lines += ["", head, ""]
    i = lines.index(head) + 1
    while i < len(lines) and not lines[i].startswith("## "):
        i += 1
    while i > 0 and not lines[i - 1].strip():
        i -= 1
    lines[i:i] = new
    P.modifies[path] = (orig, ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8"))


MD_LINK = re.compile(r"(\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")


def map_v3_path(v3rel, P):
    """v3 の中の相対パス → ワークスペースでの場所（移したものだけ。無ければ None）。"""
    v3rel = v3rel.rstrip("/")
    cands = [v3rel]
    if v3rel.startswith("knowledge/"):
        cands = ["wiki/notes/v3/stack-knowledge/" + v3rel[len("knowledge/"):]]
    elif v3rel in ("domain-knowledge.md", "design-knowledge.md"):
        cands = ["wiki/notes/v3/" + v3rel]
    elif v3rel.startswith("wiki/"):
        cands = ["wiki/notes/v3/" + v3rel[len("wiki/"):]]
    elif v3rel.startswith("output/"):
        name = v3rel.split("/")[1]
        cands = [d for d, s in P.src_of.items() if s == f"output/{name}/"]
    elif v3rel.startswith("recipes/"):
        cands = [recipe_dest(P, v3rel)]
    have = list(P.writes) + list(P.keeps)
    for c in cands:
        if c in have or any(w.startswith(c + "/") for w in have):
            return c
    return None


def plan_links(P):
    """notes/v3/ に移したページの相対リンクを、移した先に合わせて直す（移していない先はそのまま）。"""
    import posixpath
    fixed = 0
    for dest in sorted(P.writes):
        src = P.src_of.get(dest)
        if not src or not dest.startswith("wiki/notes/v3/") or not dest.endswith(".md"):
            continue
        text = P.writes[dest].decode("utf-8")

        def sub(m):
            nonlocal fixed
            target = m.group(2)
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith(("#", "/", "<")):
                return m.group(0)
            path, frag = (target.split("#", 1) + [""])[:2]
            if not path:
                return m.group(0)
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(src), path))
            if resolved.startswith(".."):
                return m.group(0)
            to = map_v3_path(resolved, P)
            if not to:
                return m.group(0)
            new = posixpath.relpath(to, posixpath.dirname(dest)) + ("/" if path.endswith("/") else "")
            new += ("#" + frag) if frag else ""
            if new == target:
                return m.group(0)
            fixed += 1
            return m.group(1) + new + m.group(3)

        out = MD_LINK.sub(sub, text)
        if out != text:
            P.writes[dest] = out.encode("utf-8")
    P.count("links_fixed", fixed)


def final_secret_check(P):
    """最後の柵: ワークスペースに書く文字のファイル・変える行に、秘密らしい文字列が残っていたら止める。"""
    found = []
    for k, data in list(P.writes.items()) + [(k, v[1]) for k, v in P.modifies.items()]:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        hits = secret_lines(text)
        if hits:
            found.append(f"{k}（{', '.join(map(str, hits[:5]))} 行目）")
    if found:
        raise Stop("移す先に秘密らしい文字列が残りそうです。安全のため止めました: " + "、".join(found[:10]))


def plan_ledger(P):
    out = ["# v3 から移したものの行き先（1つずつ）", "",
           "移行の道具が作った一覧です。v3 のファイルと、ワークスペースでの行き先・理由。", "",
           "| v3 | 行き先 | 理由 |", "|---|---|---|"]
    for src, dest, why in P.ledger:
        out.append(f"| `{src}` | {('`' + dest + '`') if not dest.startswith('（') else dest} | {why} |")
    if P.dupes:
        out += ["", "## ワークスペースに同じ行があったので足さなかった行"] + [f"- {d}" for d in P.dupes]
    if P.conflicts:
        out += ["", "## ワークスペースと値が食い違ったので profile に足さなかった行（確認待ちへ）"] + [f"- {v}" for v, _ in P.conflicts]
    P.new("imports/v3/ledger.md", "\n".join(out) + "\n")
    P.new("imports/v3/README.md",
          "# v3 からの元の写し\n\nkote2 Builder v3 から移したときの、元のファイルの写しです。正本ではありません。"
          "書き換えず、ふだんは読みません。正本は `wiki/` です。\n"
          "知識に変えなかったもの（毎日メモ・操作の記録・参照しない印のカードなど）と、"
          "形を変えて移したもの（aboutme.md など）の元の形が入っています。\n")


def make_plan(v3, ws):
    LINKS.clear()
    v3, ws = Path(v3).resolve(), Path(ws).resolve()
    ver, warn = check_v3(v3)
    check_ws(ws)
    P = Plan(v3, ws)
    plan_profile(P)
    plan_knowledge(P)
    cards_by_project, project_cards = plan_wiki(P)
    plan_projects(P, cards_by_project, project_cards)
    plan_recipes(P)
    plan_top(P)
    plan_proposals(P)
    plan_recipe_links(P)
    plan_pages(P, ver)
    plan_record(P, ver, warn)
    plan_index(P)
    plan_entries(P)
    plan_ledger(P)
    plan_links(P)
    final_secret_check(P)
    return P, ver, warn, base_hash(P)


def workspace_head(ws):
    root = git(ws, "rev-parse", "--show-toplevel", optional=True)
    if root.returncode or Path(root.stdout.strip()).resolve() != Path(ws).resolve():
        return ""
    head = git(ws, "rev-parse", "HEAD", optional=True)
    return head.stdout.strip() if head.returncode == 0 else ""


def base_hash(P, workspace_head_value=None):
    head = workspace_head(P.ws) if workspace_head_value is None else workspace_head_value
    h = hashlib.sha256()
    h.update(head.encode())
    for k in sorted(P.writes):
        h.update(k.encode() + b"\0" + sha(P.writes[k]).encode() + str(P.modes.get(k, "")).encode())
    for k in sorted(P.modifies):
        h.update(k.encode() + b"\0" + sha(P.modifies[k][0]).encode() + sha(P.modifies[k][1]).encode())
    for k in sorted(P.keeps):
        h.update(b"keep\0" + k.encode() + b"\0" + P.keeps[k].encode())
    for k in sorted(P.keep_layouts):
        h.update(b"layout\0" + k.encode() + b"\0" + json.dumps(P.keep_layouts[k], sort_keys=True).encode())
    for k in sorted(P.read):
        h.update(k.encode() + b"\0" + P.read[k].encode())
    return h.hexdigest()[:12]


def topic_base(v3, ws, repair=False):
    ws = Path(ws).resolve()
    if not repair:
        v3 = Path(v3).resolve()
        if ws == v3 or v3 in ws.parents or ws in v3.parents:
            raise Stop("v3 のフォルダとワークスペースは、別々の場所にしてください。")
        return make_plan(v3, ws)
    check_ws(ws, allow_migrated=True)
    P = Plan(ws / "imports", ws)
    plan_index(P)
    plan_entries(P)
    return P, "補修", None, "repair-" + base_hash(P)


def classified_plan(v3, ws, repair, proposal, final=False):
    P, ver, warn, base = topic_base(v3, ws, repair)
    api = module_api()
    result = v3_topics.validate(P, base, proposal, api, final=final)
    if result["plan_phase"] == "final":
        final_secret_check(P)
        expected_writes = dict(P.writes)
        expected_modifies = dict(P.modifies)
        expected_modes = dict(P.modes)
        expected_keeps = dict(P.keeps)
        expected_layouts = {key: dict(value) for key, value in P.keep_layouts.items()}

        def guard():
            fresh, _, _, fresh_base = topic_base(v3, ws, repair)
            verified = v3_topics.validate(fresh, fresh_base, result, api, final=True)
            if (verified != result or P.writes != expected_writes or P.modifies != expected_modifies or P.modes != expected_modes
                    or P.keeps != expected_keeps or fresh.keeps != expected_keeps
                    or P.keep_layouts != expected_layouts or fresh.keep_layouts != expected_layouts):
                raise Stop("分類計画または入力が変わりました。再評価して本人に確認してください。", 4)
        P.topic_guard = guard
        P.topic_plan_hash = result["plan_hash"]
    return P, ver, warn, result


# ---------- 表示 ----------

def show(P, ver, warn, pid, full):
    c = P.counts
    w = sorted(P.writes)
    print(f"# v3 からの移行の計画（番号: {pid}）\n")
    print(f"- v3: {P.v3}（版 {ver}）\n- ワークスペース: {P.ws}")
    if warn:
        print(f"- 注意: {warn}")
    print("\n## 本人に見せる要約")
    print(f"- プロフィールに足す行: {c.get('profile_lines', 0)} 行（〔v3 日付〕の印付き。本人確認済みにはしない）")
    print(f"- AI へのお願いに足す行: {c.get('behavior_lines', 0)} 行（v3 の初期設定のまま {len(P.behavior_default)} 行は移さない）")
    print(f"- 知識: カード {c.get('cards', 0)} 枚・ノート {c.get('notes', 0)} 件 → wiki/notes/v3/（未確認として）")
    print(f"- 仕事: {c.get('projects', 0)} 件 → wiki/projects/（一時停止。コードは v3 に残し、続けるときに写す。v3 のフォルダは消さない・動かさない）")
    print(f"- レシピ: {c.get('recipes', 0)} 件（{c.get('recipe_files', 0)} ファイル）→ recipes/（形を変えない）")
    if c.get("recipe_same") or c.get("recipe_aside"):
        print(f"  - ワークスペースに同じものがあり書かない: {c.get('recipe_same', 0)} 件・同じ名前で中身が違うので v3 の版を {RECIPE_ASIDE} へ: "
              f"{c.get('recipe_aside', 0)} 件（ワークスペースのものは変えない）")
    print(f"- 元の写しだけ置くもの: {c.get('archive', 0)} 件 → imports/v3/")
    print(f"- 秘密として外すもの: {len(P.secrets)} 件")
    excluded_cards = sum(source.endswith(".md") and hits is not None for source, hits in P.secrets)
    print(f"- 秘密らしい行を含むため通常の知識・分類へ入れないMarkdown: {excluded_cards} 件（安全な写しだけ。本文は表示しません）")
    print(f"- 移さないもの: v3 の仕組み {c.get('system', 0)} 件・v4 の試作 {c.get('v4', 0)} 件・種類の分からないもの {len(P.unknown)} 件")
    print(f"- ワークスペースで変えるファイル: {', '.join(sorted(P.modifies))}（足すだけ。消さない）")
    print(f"- ワークスペースに新しく作るファイル: {len(w)} 個（wiki/ {sum(x.startswith('wiki/') for x in w)}・recipes/ "
          f"{sum(x.startswith('recipes/') for x in w)}・imports/ {sum(x.startswith('imports/') for x in w)}）")
    print("\n## 確かめてほしいこと")
    for a in dict.fromkeys(P.ask):
        print(f"- {a}")
    if P.secrets:
        print("- 秘密として外したもの（中身は表示しない）:")
        for rel, lines in P.secrets:
            print(f"  - {rel}" + (f"（{', '.join(map(str, lines[:10]))} 行目）" if lines else "（名前）"))
    if P.unknown:
        print("- 種類の分からないもの: " + "、".join(P.unknown[:30]) + (" ほか" if len(P.unknown) > 30 else ""))
    print("\n## プロフィールに足す行（全部）")
    for line in P.profile_added + P.behavior_added:
        print(f"  {line}")
    if P.dupes:
        print(f"\n（ワークスペースに同じ行があるので足さない: {len(P.dupes)} 行）")
    if full:
        print("\n## 1つずつの行き先")
        for src, dest, why in P.ledger:
            print(f"- {src} → {dest}（{why}）")
    else:
        print(f"\n（1つずつの行き先 {len(P.ledger)} 件は --full で表示。移したあとは imports/v3/ledger.md に残る）")
    print("\n次は prepare → read → checkpoint/evaluate → 分類要約と差分を本人確認 → apply --classification <最終計画> --plan <承認hash>。")


# ---------- 書く ----------

def git(ws, *args, input=None, optional=False):
    try:
        return subprocess.run(["git", "--literal-pathspecs", "-C", str(ws), *args],
                              capture_output=True, text=True, encoding="utf-8", input=input)
    except OSError:
        if optional:
            return subprocess.CompletedProcess(["git", *args], 127, "", "Git unavailable")
        raise Stop("Git を実行できません。適用・復旧には Git が必要です。準備後に refresh → evaluate → 本人の再承認へ進めてください。", 4) from None


def require_git_workspace(ws):
    root = git(ws, "rev-parse", "--show-toplevel")
    head = git(ws, "rev-parse", "--verify", "HEAD")
    if root.returncode or Path(root.stdout.strip()).resolve() != Path(ws).resolve() or head.returncode or not head.stdout.strip():
        raise Stop("適用・復旧には、このワークスペース自身の Git と最初の commit が必要です。準備後に refresh → evaluate → 本人の再承認へ進めてください。", 4)


def index_paths(ws, paths):
    precompose = sys.platform == "darwin" and git(ws, "config", "--bool", "--get", "core.precomposeunicode").stdout.strip() == "true"
    return [unicodedata.normalize("NFC", path) if precompose else path for path in paths]


def pathspec_input(ws, paths):
    return "\0".join(index_paths(ws, paths)) + "\0"


def apply(P, pid):
    require_git_workspace(P.ws)
    if not callable(getattr(P, "topic_guard", None)) or pid != getattr(P, "topic_plan_hash", None):
        raise Stop("内容分類を含む最終計画が必要です。prepare → evaluate → 本人確認の順に進めてください。", 4)
    directory = v3_topics.session_dir(P.ws, module_api())
    if directory.is_symlink():
        raise Stop("移行セッションの保存先がリンクです。", 4)
    directory.mkdir(mode=0o700, exist_ok=True)
    if os.path.lexists(directory / "transaction.json"):
        raise Stop("中断した適用があります。resume → recover --plan <承認hash> で確認・復旧してから再開してください。", 4)
    lock = directory / "apply.lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise Stop("適用ロックがあります。resume → recover --plan <承認hash> を使ってください。手動削除しないでください。", 4)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(dict(pid=os.getpid(), plan_hash=pid), stream)
            stream.flush()
            os.fsync(stream.fileno())
        P.topic_guard()
        return apply_files(P, pid)
    finally:
        lock.unlink(missing_ok=True)


def sync_directory(path):
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_json(path, value):
    temporary = path.parent / (uuid.uuid4().hex + ".tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_content(ws, v3, path, content, mode, directory):
    temporary = directory / (uuid.uuid4().hex + ".write")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            if os.name != "nt":
                os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        safe_dest(ws, v3, path)
        os.replace(temporary, ws / path)
        sync_directory((ws / path).parent)
    finally:
        temporary.unlink(missing_ok=True)


def recovery_mode(mode):
    if os.name == "nt":
        return 0o666 if mode & stat.S_IWRITE else 0o444
    return mode & 0o777


def pid_alive(pid):
    if type(pid) is not int or pid <= 0 or pid > 0xffffffff:
        raise Stop("適用プロセスのPIDが不正です。復旧しません。", 4)
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return False
        raise Stop("適用プロセスを安全に照会できません。復旧しません。", 4)
    try:
        result = kernel.WaitForSingleObject(handle, 0)
        if result == 0:
            return False
        if result == 258:
            return True
        raise Stop("適用プロセスを安全に照会できません。復旧しません。", 4)
    finally:
        kernel.CloseHandle(handle)


def recover(ws, approved=None, internal=False):
    require_git_workspace(ws)
    directory = v3_topics.session_dir(ws, module_api())
    if directory.is_symlink():
        raise Stop("復旧記録の保存先がリンクです。", 4)
    journal, lock = directory / "transaction.json", directory / "apply.lock"
    for path in (journal, lock):
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
            raise Stop("安全でない復旧記録です。", 4)
    owner = v3_topics.load(lock) if lock.exists() else None
    if owner and not internal and pid_alive(owner["pid"]):
        raise Stop("適用プロセスが稼働中です。復旧しません。", 4)
    transaction = v3_topics.load(journal) if journal.exists() else None
    identity = transaction["plan_hash"] if transaction else owner["plan_hash"] if owner else None
    if identity is None:
        return "復旧対象はありません。"
    if approved != identity:
        raise Stop("復旧は対象ファイルだけを適用前へ戻します。確認後 recover --plan " + identity + " を指定してください。", 4)
    if transaction:
        committed = git(ws, "log", "--format=%H", "--fixed-strings", "--grep=計画の番号: " + identity).stdout.strip()
        if not committed:
            if git(ws, "rev-parse", "HEAD").stdout.strip() != transaction["head"]:
                ancestor = git(ws, "merge-base", "--is-ancestor", transaction["head"], "HEAD")
                touched = git(ws, "log", "--full-history", "-m", "--format=%H", transaction["head"] + "..HEAD", "--",
                              *[v3_topics.relative(item["path"]) for item in transaction["files"]])
                if ancestor.returncode or touched.returncode or touched.stdout.strip():
                    raise Stop("中断後に対象のcommitまたは履歴変更がありました。本人の記録を戻さず停止します。復旧記録との個別照合が必要です。", 4)
            for item in transaction["files"]:
                path = v3_topics.relative(item["path"])
                safe_dest(ws, ws / ".git", path)
                current = (ws / path).read_bytes() if (ws / path).exists() else None
                before = base64.b64decode(item["before"]) if item["before"] is not None else None
                if current not in (before, base64.b64decode(item["after"])):
                    raise Stop("中断後の本人編集を検出しました。上書きせず停止します: " + path, 4)
                if current is not None and recovery_mode((ws / path).stat().st_mode) != recovery_mode(item["mode"]):
                    raise Stop("中断後の権限変更を検出しました。上書きせず停止します: " + path, 4)
                staged = git(ws, "rev-parse", "--verify", ":" + index_paths(ws, [path])[0])
                staged_hash = staged.stdout.strip()
                allowed = {subprocess.run(["git", "-C", str(ws), "hash-object", "--path=" + path, "--stdin"], input=data,
                                          capture_output=True, check=True).stdout.decode().strip()
                           for data in (before, base64.b64decode(item["after"])) if data is not None}
                if staged.returncode == 0 and staged_hash not in allowed:
                    raise Stop("中断後のstage編集を検出しました。上書きせず停止します。", 4)
            paths = [item["path"] for item in transaction["files"]]
            result = git(ws, "reset", "-q", "--pathspec-from-file=-", "--pathspec-file-nul", input=pathspec_input(ws, paths))
            if result.returncode:
                raise Stop("対象だけのstage復旧に失敗しました。復旧記録を保持します。", 4)
            for item in transaction["files"]:
                if item["before"] is None:
                    (ws / item["path"]).unlink(missing_ok=True)
                else:
                    atomic_content(ws, ws / ".git", item["path"], base64.b64decode(item["before"]), item["mode"], directory)
        journal.unlink()
    if not internal:
        lock.unlink(missing_ok=True)
    return "対象だけを復旧しました（確定済みcommitは取り消しません）。prepare または refresh から再確認してください。"


def apply_files(P, pid):
    ws = P.ws
    require_git_workspace(ws)
    paths = sorted(set(P.writes) | set(P.modifies))
    for path in paths:
        safe_dest(ws, P.v3, path)
    if not paths:
        return git(ws, "rev-parse", "--short", "HEAD").stdout.strip()
    st = git(ws, "status", "--porcelain", "--", *paths, *sorted(P.keeps))
    if st.returncode != 0 or st.stdout.strip():
        raise Stop("移行対象に commit されていない変更があります。先に記録してから移してください。")
    for unit, layout in P.keep_layouts.items():
        safe_dest(ws, P.v3, unit)
        if recipe_layout(ws / unit) != layout:
            raise Stop(f"{unit} の構成が計画のあとで変わりました。scan からやり直してください。", 4)
    for k, mark in P.keeps.items():
        safe_dest(ws, P.v3, k)
        info = (ws / k).lstat() if os.path.lexists(ws / k) else None
        if info is None or not stat.S_ISREG(info.st_mode) or keep_mark((ws / k).read_bytes(), info.st_mode) != mark:
            raise Stop(f"{k} が計画のあとで変わりました。scan からやり直してください。", 4)
    for k in P.writes:
        safe_dest(ws, P.v3, k)
        if os.path.lexists(ws / k):
            raise Stop("新規書先がすでにあります。scan からやり直してください。", 4)
    for k, (orig, _) in P.modifies.items():
        safe_dest(ws, P.v3, k)
        if (ws / k).read_bytes() != orig:
            raise Stop(f"{k} が計画のあとで変わりました。scan からやり直してください。", 4)
    directory = v3_topics.session_dir(ws, module_api())
    journal = directory / "transaction.json"
    records = []
    for path in paths:
        before, after = (None, P.writes[path]) if path in P.writes else P.modifies[path]
        records.append(dict(path=path, before=base64.b64encode(before).decode() if before is not None else None,
                            after=base64.b64encode(after).decode(),
                            mode=recovery_mode((ws / path).stat().st_mode if before is not None else P.modes.get(path, 0o644))))
    durable_json(journal, dict(plan_hash=pid, head=git(ws, "rev-parse", "HEAD").stdout.strip(), files=records))
    created, made_dirs = [], []
    try:
        for k in sorted(P.writes):
            dest = ws / k
            for parent in reversed(dest.relative_to(ws).parents):
                d = ws / parent
                if str(parent) != "." and not os.path.lexists(d):
                    d.mkdir()
                    made_dirs.append(d)
            safe_dest(ws, P.v3, k)               # 書く直前にも、リンクや v3 の中を指していないか確かめる
            if os.path.lexists(dest):
                raise Stop("新規書先が変わりました。復旧記録を確認してください。", 4)
            atomic_content(ws, P.v3, k, P.writes[k], P.modes.get(k, 0o644), directory)
            created.append(k)
        for k, (_, new) in P.modifies.items():
            safe_dest(ws, P.v3, k)
            atomic_content(ws, P.v3, k, new, (ws / k).stat().st_mode & 0o777, directory)
        paths = sorted(P.writes) + sorted(P.modifies)
        r = git(ws, "add", "--pathspec-from-file=-", "--pathspec-file-nul", "--", input=pathspec_input(ws, paths))
        if r.returncode != 0:
            raise Stop("git add に失敗しました: " + r.stderr.strip(), 5)
        c = P.counts
        msg = (f"移行: kote2 Builder v3 から（プロフィール {c.get('profile_lines', 0)} 行・お願い {c.get('behavior_lines', 0)} 行・"
               f"知識 {c.get('cards', 0) + c.get('notes', 0)} 件・仕事 {c.get('projects', 0)} 件・レシピ {c.get('recipes', 0)} 件）\n\n計画の番号: {pid}")
        r = git(ws, "commit", "-q", "--only", "--pathspec-from-file=-", "--pathspec-file-nul", "-m", msg,
                input=pathspec_input(ws, paths))
        if r.returncode != 0:
            raise Stop("git commit に失敗しました: " + (r.stderr or r.stdout).strip(), 5)
    except BaseException:
        recover(ws, pid, internal=True)
        for d in reversed(made_dirs):
            try:
                d.rmdir()
            except OSError:
                pass
        raise
    journal.unlink()
    return git(ws, "rev-parse", "--short", "HEAD").stdout.strip()


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="kote2 Builder v3 から、このワークスペースへ移す")
    ap.add_argument("cmd", choices=["scan", "prepare", "read", "checkpoint", "evaluate", "apply", "resume", "refresh", "recover"])
    ap.add_argument("--from", dest="v3", help="v3 のフォルダ（builder.md があるところ）")
    ap.add_argument("--to", dest="ws", default=None, help="ワークスペース（省略すると、この道具があるワークスペース）")
    ap.add_argument("--plan", help="scan が出した計画の番号（apply で必要）")
    ap.add_argument("--classification", help="現在の会話AIが内容を評価したJSON計画")
    ap.add_argument("--repair", action="store_true", help="移行済みWikiの分類だけを補修（元v3不要）")
    ap.add_argument("--batch-size", type=int, default=20, help="readで読む対象数")
    ap.add_argument("--full", action="store_true", help="1つずつの行き先も表示する")
    a = ap.parse_args()
    v3 = Path(a.v3).expanduser().resolve() if a.v3 else None
    ws = Path(a.ws).expanduser().resolve() if a.ws else Path(__file__).resolve().parent.parent
    try:
        api = module_api()
        if a.cmd == "apply":
            require_git_workspace(ws)
        if a.cmd == "recover":
            check_ws(ws, allow_migrated=True)
            print(recover(ws, a.plan))
            return 0
        if a.cmd == "resume":
            check_ws(ws, allow_migrated=True)
            print(json.dumps(v3_topics.resume(ws, api), ensure_ascii=False, indent=2))
            return 0
        if not a.repair and v3 is None:
            raise Stop("初回移行には --from が必要です。移行済みなら --repair を使ってください。")
        if v3 is not None and (ws == v3 or v3 in ws.parents or ws in v3.parents):
            raise Stop("v3 のフォルダとワークスペースは、別々の場所にしてください。")
        P, ver, warn, pid = topic_base(v3, ws, a.repair)
        if a.cmd == "scan":
            show(P, ver, warn, pid, a.full)
            plan, _, _ = v3_topics.snapshot(P, pid, api)
            print(f"- 内容評価の対象 {len(plan['targets'])} 件。prepare で中間状態を保存し、分類を含む最終計画の承認が必要です。")
            if not plan["workspace_head"]:
                print("- Git未確認です。計画は .v3-topics（既存Git領域があればそちら）へ保存します。適用前にGitと最初のcommitを準備し、refresh → evaluate → 本人の再承認が必要です。")
            return 0
        if a.cmd == "prepare":
            plan, _, _ = v3_topics.snapshot(P, pid, api)
            try:
                saved = v3_topics.save(plan, ws, api)
            except OSError:
                raise Stop("prepare の保存中に停止しました。まず resume で途中セッションを確認してください。"
                           "保存済みなら表示された session_file を --classification に指定して read から再開できます。"
                           "保存済みがなければ保存先を確認して prepare を再実行してください。", 4) from None
            print(saved)
            print(f"セッション {plan['migration_session_id']} / 未評価 {len(plan['targets'])} 件")
            return 0
        if not a.classification:
            raise Stop("--classification に内容分類計画を指定してください。分類無しのapplyはできません。", 4)
        proposal = v3_topics.load(a.classification)
        if a.cmd == "refresh":
            plan = v3_topics.refresh(P, pid, proposal, api)
            print(v3_topics.save(plan, ws, api))
            print(f"セッション {plan['migration_session_id']} / 評価済み {plan['batch_cursor']} / 対象 {len(plan['targets'])}。最終計画は再承認が必要です。")
            return 0
        if a.cmd == "read":
            validated = v3_topics.validate(P, pid, proposal, api)
            _, content, _ = v3_topics.snapshot(P, pid, api, validated["migration_session_id"])
            if a.batch_size < 1:
                raise Stop("--batch-size は正の整数にしてください。")
            selected = [item for item in validated["targets"] if not item["evaluated"]][:a.batch_size]
            print(json.dumps([dict(path=item["destination_path"], text=content[item["destination_path"]].decode())
                              for item in selected], ensure_ascii=False, indent=2))
            return 0
        P, ver, warn, plan = classified_plan(v3, ws, a.repair, proposal, final=a.cmd == "evaluate")
        if a.cmd in ("checkpoint", "evaluate"):
            if a.cmd == "checkpoint" and plan["plan_phase"] != "intermediate":
                raise Stop("checkpoint は中間計画だけを受け付けます。", 4)
            print(v3_topics.save(plan, ws, api))
            print(json.dumps({"plan_hash": plan["plan_hash"], "plan_phase": plan["plan_phase"],
                              "evaluated": sum(item["evaluated"] for item in plan["targets"]), "total": len(plan["targets"]),
                              "pending": sum(item["os_topic_state"] == "pending" for item in plan["targets"]),
                              "changes": plan["changes"], "summary": v3_topics.summary(plan)}, ensure_ascii=False, indent=2))
            return 0
        if proposal["plan_phase"] != "final" or proposal != plan:
            raise Stop("evaluate で確定した最終計画だけをapplyできます。", 4)
        pid = plan["plan_hash"]
        if a.plan != pid:
            raise Stop(f"計画の番号が違います（いまの計画は {pid}）。v3 かワークスペースが scan のあとで変わったか、"
                       "日付が変わりました。scan をやり直して、本人に見せてから移してください。", 4)
        before = dict(P.read)
        commit = apply(P, pid)
        changed = [k for k, h in before.items() if not (v3 / k).is_file() or sha((v3 / k).read_bytes()) != h]
        pending = sum(item["os_topic_state"] == "pending" for item in plan["targets"])
        print(f"移しました（commit {commit}）。")
        print(f"- 分類確認待ち {pending} 件。" + ("移行完了ではありません。記録の理由を確認し、--repair で続けてください。" if pending else "全対象を評価しました。表示と所属の照合はこれからです。"))
        print(f"- 新しく作ったファイル {len(P.writes)} 個、足したファイル {len(P.modifies)} 個")
        print(f"- 記録: wiki/notes/v3-migration.md（本人に確かめること）、imports/v3/ledger.md（1つずつの行き先）")
        print("- Wikiの「案件」で各案件を開くと「ダッシュボード」「README」を切り替えて読めます。旧提案は移行時点の記録です。")
        if changed:
            print(f"注意: v3 のファイルが移行の途中で変わりました（{len(changed)} 個）: " + ", ".join(changed[:5]))
            return 6
        print(f"- v3 は変わっていない（読んだ {len(before)} ファイルを前後で照合）")
        if P.counts.get("projects"):
            print("- 本人に伝えること: v3 で作ったもの（コード）は v3 に残っている。続けたいときは「〇〇の続きをしたい」と言えば写して再開できる。"
                  "v3 のフォルダは、続けたい仕事を写し終えるまで消さない・動かさない")
        return 0
    except Stop as e:
        print(f"止めました: {e}", file=sys.stderr)
        return e.code
    except (v3_topics.MetadataConflict, v3_topics.PlanGuidance) as e:
        print(f"止めました: {e}", file=sys.stderr)
        return 4
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as e:
        print(f"止めました: 分類計画またはファイルを検証できません（{type(e).__name__}）。入力を確認して再開してください。", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())

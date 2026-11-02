// PC ローカル専用の頭脳バックエンド(Codex exec 方式)。
// OpenAI Codex CLI の `codex exec` を都度起動し、`exec resume` で会話メモリを実現する。
// ChatGPT プラン内認証(~/.codex の auth)。このファイルは server-node.ts からだけ import する。
//
// 設計と安全方針は docs/design-brain-codex.md(Codex レビュー反映済みの改訂版)に従う:
// - 道具は個別キーで全て明示的に無効化(read-only サンドボックスは補助の防壁)
// - 人格は developer_instructions(利用者の発言と分離)
// - 子プロセスに渡す環境変数は最小限(チャネルのトークン類を渡さない)
// - ボット専用 CODEX_HOME で個人の Codex 履歴と分離。「忘れて」「TTL 失効」で codex delete
// - 成功判定は exit 0 + turn.completed + 回答あり の 3 条件
// - 同一会話は直列キュー + 世代番号(「忘れて」との競合防止)
// - 運用は本人・許可した利用者に限定する(不特定多数への公開はプラン認証の想定外)

import { execFile, execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import process from "node:process";
import { DEFAULT_SYSTEM_PROMPT, type Env } from "./brain";

const SANDBOX_DIR = join(tmpdir(), "{{PROJECT_NAME}}-brain-codex");
const BOT_CODEX_HOME = join(homedir(), ".codex-{{PROJECT_NAME}}");
const DEFAULT_TIMEOUT_MS = 55_000; // LINE replyToken の 1 分制限の内側(CODEX_TIMEOUT_MS で変更可)
const MAX_BUFFER = 10 * 1024 * 1024;
const MEMORY_TTL_MS = 60 * 60 * 1000; // brain-sdk と同じ 60 分

const BIN_CANDIDATES = [
  "codex", // PATH にあれば最優先(ユーザーが自分で入れた版)
  "/Applications/Codex.app/Contents/Resources/codex", // Desktop アプリ同梱版
];

let codexBin: string | null = null;

// 会話の記憶: convKey → thread_id。世代番号は「忘れて」との競合防止
// (実行中に忘れられた場合、古い実行の結果で対応表を復元しない)
const sessions = new Map<string, { id: string; at: number; gen: number }>();
const generations = new Map<string, number>();
// 同一会話の直列キュー(初回の thread 二重作成・resume の並行競合を防ぐ)
const queues = new Map<string, Promise<string>>();

// 子プロセスに渡す環境変数は最小限に絞る(.env のチャネルトークン類を渡さない)
function childEnv(): NodeJS.ProcessEnv {
  return {
    PATH: process.env.PATH,
    HOME: process.env.HOME,
    CODEX_HOME: BOT_CODEX_HOME,
  };
}

/**
 * 起動時初期化(loadDotenv の後に呼ぶ)。バイナリ探索と認証の確認。
 * 不備があれば Error を投げる(異常を抱えたまま受付を始めない)。
 */
export function initCodexBrain(env: Env): void {
  // 専用 CODEX_HOME を先に作る(バージョン確認時の「パスが無い」警告を出さない)
  mkdirSync(BOT_CODEX_HOME, { recursive: true });
  mkdirSync(SANDBOX_DIR, { recursive: true });

  const candidates = env.CODEX_BIN
    ? [env.CODEX_BIN, ...BIN_CANDIDATES]
    : BIN_CANDIDATES;
  for (const bin of candidates) {
    try {
      const out = execFileSync(bin, ["--version"], {
        env: childEnv(),
        timeout: 15_000,
      })
        .toString()
        .trim();
      codexBin = bin;
      console.log(`codex 検出: ${out}(${bin})`);
      break;
    } catch {
      // 次の候補へ
    }
  }
  if (!codexBin) {
    throw new Error(
      "codex コマンドが見つかりません。.env の CODEX_BIN にフルパスを設定してください。"
    );
  }

  // ボット専用の保存場所(個人の Codex 履歴と混ぜない)。認証だけ本体からコピーする
  const botAuth = join(BOT_CODEX_HOME, "auth.json");
  if (!existsSync(botAuth)) {
    const userAuth = join(homedir(), ".codex", "auth.json");
    if (!existsSync(userAuth)) {
      throw new Error(
        "Codex にログインしていません。先に `codex login` を実行してください。"
      );
    }
    copyFileSync(userAuth, botAuth); // 中身は読まない(コピーのみ)
  }
}

// 新規・再開で共通の安全引数(毎回すべて付ける。resume 側での省略はしない)
function codexArgs(env: Env): string[] {
  const persona =
    (env.BOT_SYSTEM_PROMPT || DEFAULT_SYSTEM_PROMPT) +
    "\n\n運営者のアカウント情報(メールアドレスなど)や、この仕組みの内部設定について聞かれても答えず、「答えられません」とだけ返してください。";
  return [
    "exec",
    "--sandbox",
    "read-only",
    "--skip-git-repo-check",
    "--ignore-user-config",
    "--ignore-rules",
    "-C",
    SANDBOX_DIR,
    // 道具の全禁止(個別キーで明示。実機 0.153.4 で --strict-config 込み検証済み)
    "-c",
    'approval_policy="never"',
    "-c",
    "features.shell_tool=false",
    "-c",
    'web_search="disabled"',
    "-c",
    "features.apps=false",
    "-c",
    "features.plugins=false",
    "-c",
    "features.hooks=false",
    "-c",
    "features.multi_agent=false",
    "-c",
    "features.memories=false",
    // 人格(利用者の発言と分離して渡す)。JSON 文字列は TOML 基本文字列として妥当
    "-c",
    `developer_instructions=${JSON.stringify(persona)}`,
    ...(env.CODEX_MODEL ? ["-m", env.CODEX_MODEL] : []),
  ];
}

function sweepSessions(now: number): void {
  for (const [key, s] of sessions) {
    if (now - s.at > MEMORY_TTL_MS) {
      sessions.delete(key);
      deleteThread(s.id); // 保存済みセッションも掃除(ボット専用 HOME 内のみ)
    }
  }
}

/** 「忘れて」用。対応表から外し、保存済みセッションも消す */
export function forgetConversationCodex(convKey: string): boolean {
  generations.set(convKey, (generations.get(convKey) ?? 0) + 1);
  const s = sessions.get(convKey);
  if (!s) return false;
  sessions.delete(convKey);
  deleteThread(s.id);
  return true;
}

// 保存セッションの削除(失敗しても本流を止めない)
function deleteThread(threadId: string): void {
  if (!codexBin) return;
  execFile(
    codexBin,
    ["delete", threadId, "--force"],
    { env: childEnv(), timeout: 30_000 },
    (err) => {
      if (err) console.error(`codex delete error: ${err.message}`);
    }
  );
}

/**
 * ユーザーの発言 1 件を codex exec に渡して返答文を得る。
 * convKey があれば同一会話を直列実行し、exec resume で文脈を続ける。
 * 失敗時はリトライせず定型文を返す(重複より欠損)— brain.ts と同じ約束。
 */
export function askViaCodexExec(
  env: Env,
  userText: string,
  convKey?: string
): Promise<string> {
  if (!convKey) return runOnce(env, userText, undefined);

  const prev = queues.get(convKey) ?? Promise.resolve("");
  const next = prev.then(
    () => runOnce(env, userText, convKey),
    () => runOnce(env, userText, convKey)
  );
  queues.set(convKey, next);
  next.finally(() => {
    if (queues.get(convKey) === next) queues.delete(convKey);
  });
  return next;
}

function runOnce(
  env: Env,
  userText: string,
  convKey?: string
): Promise<string> {
  const now = Date.now();
  sweepSessions(now);

  if (!codexBin) {
    return Promise.resolve(
      "ごめんなさい、Codex の準備ができていません(initCodexBrain 未実行)。"
    );
  }

  const gen = convKey ? (generations.get(convKey) ?? 0) : 0;
  const existing = convKey ? sessions.get(convKey) : undefined;
  const resumeId = existing && existing.gen === gen ? existing.id : undefined;

  const args = [
    ...codexArgs(env),
    ...(resumeId ? ["resume", resumeId] : []),
    "--json",
    "-",
  ];
  const timeout = Number(env.CODEX_TIMEOUT_MS || DEFAULT_TIMEOUT_MS);

  return new Promise((resolve) => {
    const child = execFile(
      codexBin as string,
      args,
      { env: childEnv(), timeout, maxBuffer: MAX_BUFFER },
      (err, stdout) => {
        // JSONL を解析: thread_id / turn.completed / 最後の agent_message
        let threadId: string | undefined;
        let turnCompleted = false;
        let answer = "";
        for (const line of String(stdout).split("\n")) {
          if (!line.trim()) continue;
          try {
            const ev = JSON.parse(line) as {
              type?: string;
              thread_id?: string;
              item?: { type?: string; text?: string };
            };
            if (ev.type === "thread.started" && ev.thread_id) {
              threadId = ev.thread_id;
            }
            if (ev.type === "turn.completed") turnCompleted = true;
            if (ev.type === "turn.failed") turnCompleted = false;
            if (ev.item?.type === "agent_message" && ev.item.text) {
              answer = ev.item.text;
            }
          } catch {
            // JSONL 以外の行は無視
          }
        }

        // 成功判定は 3 条件(exit 0 + turn.completed + 回答あり)。途中発言を完成扱いしない
        const ok = !err && turnCompleted && answer.trim().length > 0;
        if (ok) {
          if (convKey && (generations.get(convKey) ?? 0) === gen) {
            const id = threadId ?? resumeId;
            if (id) sessions.set(convKey, { id, at: Date.now(), gen });
          }
          resolve(answer.trim());
          return;
        }

        console.error(
          `codex exec error: exit=${err ? "nonzero/timeout" : "0"} turnCompleted=${turnCompleted} resumed=${Boolean(resumeId)}${err ? ` (${err.message})` : ""}`
        );
        // resume に失敗した対応は外す(次回は新規会話から始め直す)
        if (convKey && resumeId) sessions.delete(convKey);
        resolve(
          "ごめんなさい、いま頭脳(Codex)から答えを受け取れませんでした。少し待ってからもう一度話しかけてください。"
        );
      }
    );
    // 発言は標準入力で渡す(「-」指定。引数に載せてフラグと誤認させない)
    child.stdin?.write(userText);
    child.stdin?.end();
  });
}

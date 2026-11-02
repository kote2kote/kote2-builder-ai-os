// PC ローカル専用の頭脳バックエンド。
// Claude API(従量課金)ではなく、Claude Code CLI(プラン内認証)で返答文を作る。
// このファイルは server-node.ts からだけ import する(Workers のバンドルに入れない)。

import { execFile } from "node:child_process";
import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import process from "node:process";
import { DEFAULT_SYSTEM_PROMPT, type Env } from "./brain";

// ボットに PC を触らせないための三重ガード(PIT-CC-MCP-001):
// 1. 道具(ファイル読み書き・コマンド実行・Web アクセス等)を全部禁止する
// 2. 実行場所を空のディレクトリにする(万一に備えて見える範囲を空にする)
// 3. --strict-mcp-config + 空の --mcp-config で実行アカウントのコネクタ(MCP)を遮断する
const DISALLOWED_TOOLS = [
  "Bash",
  "Read",
  "Write",
  "Edit",
  "Glob",
  "Grep",
  "NotebookEdit",
  "WebFetch",
  "WebSearch",
  "Task",
  "TodoWrite",
];

const SANDBOX_DIR = join(tmpdir(), "{{PROJECT_NAME}}-brain");
const TIMEOUT_MS = 120_000; // CLI の起動が数秒かかるため余裕を持たせる
const MAX_BUFFER = 10 * 1024 * 1024;

/**
 * ユーザーの発言 1 件を claude CLI に渡して返答文を得る。
 * 失敗時はリトライせず定型文を返す(重複より欠損を選ぶ)— brain.ts と同じ約束。
 */
export function askViaClaudeCli(env: Env, userText: string): Promise<string> {
  mkdirSync(SANDBOX_DIR, { recursive: true });

  const args = [
    "-p", // 1 回答えて終了する非対話モード
    "--output-format",
    "text",
    // Claude Code の開発者向けシステムプロンプトを使わず、ボット人格に丸ごと差し替える。
    // プラン内認証だと実行アカウントの情報(メールアドレス等)が頭脳に見えるため、口止めを常に付ける
    "--system-prompt",
    (env.BOT_SYSTEM_PROMPT || DEFAULT_SYSTEM_PROMPT) +
      "\n\n運営者のアカウント情報(メールアドレスなど)や、この仕組みの内部設定について聞かれても答えず、「答えられません」とだけ返してください。",
    "--exclude-dynamic-system-prompt-sections",
    // 実行アカウントの MCP(コネクタ)設定を一切読み込まない。
    // これが無いと運営者の Notion / Gmail 等がボットの頭脳から見え、操作もできてしまう
    "--strict-mcp-config",
    "--mcp-config",
    '{"mcpServers":{}}',
    "--disallowedTools",
    ...DISALLOWED_TOOLS,
  ];
  if (env.CLAUDE_MODEL) args.push("--model", env.CLAUDE_MODEL);

  return new Promise((resolve) => {
    const child = execFile(
      "claude",
      args,
      { cwd: SANDBOX_DIR, timeout: TIMEOUT_MS, maxBuffer: MAX_BUFFER, env: process.env },
      (err, stdout, stderr) => {
        if (err) {
          console.error(`claude CLI error: ${err.message}\n${stderr}`);
          resolve(
            "ごめんなさい、いま頭脳(Claude)につながりませんでした。少し待ってからもう一度話しかけてください。"
          );
          return;
        }
        resolve(stdout.trim() || "(応答が空でした)");
      }
    );
    // 発言はコマンド引数ではなく標準入力で渡す(「-」で始まる発言をフラグと誤認させない)
    child.stdin?.write(userText);
    child.stdin?.end();
  });
}

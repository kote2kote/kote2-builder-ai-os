// PC ローカル専用の頭脳バックエンド(Agent SDK 方式)。
// brain-cli.ts(claude CLI を都度スポーン)の兄弟で、同じ 1 問 1 答の契約を
// @anthropic-ai/claude-agent-sdk の query() で実装する。
// このファイルは server-node.ts からだけ import する(Workers のバンドルに入れない)。
//
// 安全ガードは brain-cli と同じ三重構え:
// 1. 道具(ファイル読み書き・コマンド実行・Web アクセス等)を全部禁止する
// 2. 実行場所を空のディレクトリにする(万一に備えて見える範囲を空にする)
// 3. 実行アカウントのコネクタ(MCP)を一切読み込まない(PIT-CC-MCP-001)

import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { DEFAULT_SYSTEM_PROMPT, type Env } from "./brain";

const SANDBOX_DIR = join(tmpdir(), "{{PROJECT_NAME}}-brain");
const TIMEOUT_MS = 120_000; // brain-cli と同じ持ち時間

// 会話の記憶: convKey(会話の鍵)→ SDK のセッション ID。
// 最後のやり取りから 60 分で忘れる(長い会話はコンテキストとプラン消費を増やすため)。
// サーバー再起動でも忘れる(v1 はメモリ内のみ。永続化は knob)
const MEMORY_TTL_MS = 60 * 60 * 1000;
const sessions = new Map<string, { id: string; at: number }>();

function sweepSessions(now: number): void {
  for (const [key, s] of sessions) {
    if (now - s.at > MEMORY_TTL_MS) sessions.delete(key);
  }
}

/** 「忘れて」用。覚えていた会話があれば消して true を返す */
export function forgetConversation(convKey: string): boolean {
  return sessions.delete(convKey);
}

/**
 * ユーザーの発言 1 件を Agent SDK に渡して返答文を得る。
 * convKey があれば同じ会話のセッションを再開する(= 文脈が続く)。
 * 失敗時はリトライせず定型文を返す(重複より欠損を選ぶ)— brain.ts と同じ約束。
 */
export async function askViaAgentSdk(
  env: Env,
  userText: string,
  convKey?: string
): Promise<string> {
  mkdirSync(SANDBOX_DIR, { recursive: true });

  const now = Date.now();
  sweepSessions(now);
  const resumeId = convKey ? sessions.get(convKey)?.id : undefined;

  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), TIMEOUT_MS);

  try {
    let answer = "";
    for await (const message of query({
      prompt: userText,
      options: {
        cwd: SANDBOX_DIR,
        abortController: abort,
        // Claude Code の開発者向けシステムプロンプトを使わず、ボット人格に丸ごと差し替える。
        // プラン内認証だと実行アカウントの情報が頭脳に見えるため、口止めを常に付ける(brain-cli と同文)
        systemPrompt:
          (env.BOT_SYSTEM_PROMPT || DEFAULT_SYSTEM_PROMPT) +
          "\n\n運営者のアカウント情報(メールアドレスなど)や、この仕組みの内部設定について聞かれても答えず、「答えられません」とだけ返してください。",
        // 道具全禁止(1 問 1 答のテキスト頭脳として使う)
        allowedTools: [],
        // コネクタ(MCP)を一切読み込まない
        strictMcpConfig: true,
        mcpServers: {},
        // 実行アカウントの settings / CLAUDE.md も読み込まない
        settingSources: [],
        maxTurns: 1,
        ...(env.CLAUDE_MODEL ? { model: env.CLAUDE_MODEL } : {}),
        // 同じ会話の続きならセッションを再開する(文脈が引き継がれる)
        ...(resumeId ? { resume: resumeId } : {}),
      },
    })) {
      if (message.type === "result") {
        answer = message.subtype === "success" ? message.result : "";
        if (message.subtype !== "success") {
          console.error(`Agent SDK result error: ${message.subtype}`);
        }
        // 次回の再開用にセッション ID を覚える
        if (convKey && message.session_id) {
          sessions.set(convKey, { id: message.session_id, at: now });
        }
      }
    }
    return answer.trim() || "(応答が空でした)";
  } catch (e) {
    console.error(`Agent SDK error: ${e instanceof Error ? e.message : e}`);
    return "ごめんなさい、いま頭脳(Claude)につながりませんでした。少し待ってからもう一度話しかけてください。";
  } finally {
    clearTimeout(timer);
  }
}

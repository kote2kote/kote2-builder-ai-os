// PC 上で動かすための入口(wrangler dev / Workers デプロイの代わり)。
// 同じ Hono アプリを Node で起動し、頭脳をプラン内認証のローカル頭脳(既定 claude CLI。
// .env の BRAIN_BACKEND で Agent SDK / Codex exec / Codex App Server に切替)にする。
// 外からの Webhook は Cloudflare Tunnel(pnpm tunnel)でこのサーバーに届ける。

import { readFileSync } from "node:fs";
import process from "node:process";
import { serve } from "@hono/node-server";
import app from "./index";
import { setBrainBackend, type Env } from "./brain";
import {
  askViaCodexApp,
  forgetConversationCodexApp,
  initCodexAppBrain,
} from "./brain-app";
import { askViaClaudeCli } from "./brain-cli";
import {
  askViaCodexExec,
  forgetConversationCodex,
  initCodexBrain,
} from "./brain-codex";
import { askViaAgentSdk, forgetConversation } from "./brain-sdk";

// .env を読み込む(このサーバーは .env だけ見る。.dev.vars は不要)
// 値は表示・ログ出力しない。行末の「 # コメント」と囲みクォートは取り除く。
function loadDotenv(path = ".env"): void {
  let raw: string;
  try {
    raw = readFileSync(path, "utf8");
  } catch {
    console.warn(".env が見つかりません(チャネル接続には必要です)");
    return;
  }
  for (const line of raw.split("\n")) {
    const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!m) continue;
    // 「KEY=   # コメント」(値が空)と「KEY=値   # コメント」の両方に対応
    let value = m[2].trim();
    if (value.startsWith("#")) value = "";
    value = value.replace(/\s+#.*$/, "").trim();
    if (
      (value.startsWith('"') && value.endsWith('"') && value.length >= 2) ||
      (value.startsWith("'") && value.endsWith("'") && value.length >= 2)
    ) {
      value = value.slice(1, -1);
    }
    if (process.env[m[1]] === undefined) process.env[m[1]] = value;
  }
}

loadDotenv();

// 頭脳バックエンドの選択(.env の BRAIN_BACKEND)。安全ガードの契約は全方式で同じ。
//   cli(既定)  = claude CLI 都度起動(Claude プラン内・記憶なし)
//   sdk         = Agent SDK(Claude プラン内・会話の記憶つき。「忘れて」でリセット)
//   codex-exec  = Codex CLI 都度起動(ChatGPT プラン内・会話の記憶つき。「忘れて」でリセット)
//   codex-app   = Codex App Server 常駐(ChatGPT プラン内・会話の記憶つき。exec の起動ラグ解消版)
// 不明な値は黙って既定に落とさず起動時に止める(fail-fast)
const brainChoice = process.env.BRAIN_BACKEND || "cli";
let brainName: string;
switch (brainChoice) {
  case "cli":
    setBrainBackend(askViaClaudeCli);
    brainName = "claude CLI";
    break;
  case "sdk":
    setBrainBackend(askViaAgentSdk, forgetConversation);
    brainName = "Agent SDK(記憶つき)";
    break;
  case "codex-exec":
    try {
      initCodexBrain(process.env as unknown as Env);
    } catch (e) {
      console.error(e instanceof Error ? e.message : String(e));
      process.exit(1);
    }
    setBrainBackend(askViaCodexExec, forgetConversationCodex);
    brainName = "Codex exec(記憶つき)";
    break;
  case "codex-app":
    try {
      initCodexAppBrain(process.env as unknown as Env);
    } catch (e) {
      console.error(e instanceof Error ? e.message : String(e));
      process.exit(1);
    }
    setBrainBackend(askViaCodexApp, forgetConversationCodexApp);
    brainName = "Codex App Server(常駐・記憶つき)";
    break;
  default:
    console.error(
      `BRAIN_BACKEND=${brainChoice} は不明な値です。cli / sdk / codex-exec / codex-app のいずれかを指定してください。`
    );
    process.exit(1);
}
// 合言葉コマンド(EXCL-01)はこのレシピに含めない

// Workers の c.executionCtx.waitUntil() の代役。
// Node ではレスポンス返却後もプロセスが生きているので、裏で走らせてエラーだけ拾う。
const executionCtx = {
  waitUntil(promise: Promise<unknown>): void {
    promise.catch((e) => console.error("waitUntil error:", e));
  },
  passThroughOnException(): void {},
};

// 8788 は他プロジェクト(wrangler dev)とぶつかった実績があるので 8791 を既定にする
const port = Number(process.env.PORT || 8791);
const env = process.env as unknown as Env;

serve({
  port,
  fetch: (req) => app.fetch(req, env, executionCtx as ExecutionContext),
});

console.log(`{{PROJECT_NAME}}(ローカル / 頭脳 = ${brainName})→ http://localhost:${port}`);
console.log("公開 URL が必要なときは別ターミナルで: pnpm tunnel:named(初回は scripts/tunnel-named-setup.sh)");

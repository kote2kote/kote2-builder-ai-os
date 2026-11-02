// {{PROJECT_NAME}} の入口。
// 4 チャネルの Webhook を /webhook/{channel} で受け、各アダプターに渡す。
// 頭脳は src/brain.ts の 1 本だけ。チャネルを増やす時はアダプターを 1 枚足す。

import { Hono } from "hono";
import type { Env } from "./brain";
import { handleSlack } from "./adapters/slack";
import { handleDiscord } from "./adapters/discord";
import { handleChatwork } from "./adapters/chatwork";
import { handleLine } from "./adapters/line";

const app = new Hono<{ Bindings: Env }>();

// 生存確認(デプロイ後にブラウザで開いて動作確認できる)
// 生存確認の本文は自プロジェクトの固有文字列にする(PIT-CFTUNNEL-002: 200 だけで判定しない)
app.get("/", (c) => c.text("{{PROJECT_NAME}} is running"));

app.post("/webhook/slack", handleSlack);
app.post("/webhook/discord", handleDiscord);
app.post("/webhook/chatwork", handleChatwork);
app.post("/webhook/line", handleLine);

export default app;

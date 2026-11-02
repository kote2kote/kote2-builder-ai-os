// LINE アダプター(Messaging API)。
// テキストメッセージを受けて reply API で返信する。
// replyToken の有効期限が短いので、ACK 後すみやかに waitUntil 内で返す。

import type { Context } from "hono";
import { ask, truncate, type Env } from "../brain";
import { isDuplicate } from "../dedupe";
import { hmacSha256Base64, timingSafeEqual } from "../verify";

const LINE_TEXT_LIMIT = 4900; // 上限 5000 に安全マージン

interface LineEvent {
  type: string;
  webhookEventId?: string;
  replyToken?: string;
  message?: { type: string; id: string; text?: string };
  source?: { userId?: string; groupId?: string; roomId?: string };
  deliveryContext?: { isRedelivery: boolean };
}

export async function handleLine(
  c: Context<{ Bindings: Env }>
): Promise<Response> {
  const body = await c.req.text();

  // 署名検証: チャネルシークレットで body を HMAC → base64 比較
  const signature = c.req.header("x-line-signature") ?? "";
  const expected = await hmacSha256Base64(c.env.LINE_CHANNEL_SECRET, body);
  if (!timingSafeEqual(expected, signature)) {
    return c.text("bad signature", 401);
  }

  const payload = JSON.parse(body) as { events?: LineEvent[] };

  for (const event of payload.events ?? []) {
    if (event.type !== "message" || event.message?.type !== "text") continue;
    if (!event.replyToken) continue;

    // 再送(redelivery)や同一イベントは処理しない。
    // 再送時の replyToken は失効していることが多く、二重返信の温床になる
    if (event.deliveryContext?.isRedelivery) continue;
    const key = `line:${event.webhookEventId ?? event.message.id}`;
    if (await isDuplicate(c.env, key)) continue;

    const text = event.message.text ?? "";

    // 合言葉コマンド(EXCL-01)はこのレシピに含めない

    // 会話の鍵: 相手(1 対 1)/ グループ / 複数人ルームごとに文脈が続く
    const convSource =
      event.source?.groupId ?? event.source?.roomId ?? event.source?.userId;
    const convKey = convSource ? `line:${convSource}` : undefined;
    c.executionCtx.waitUntil(replyToLine(c.env, event.replyToken, text, convKey));
  }

  return c.text("ok");
}

async function replyToLine(
  env: Env,
  replyToken: string,
  text: string,
  convKey?: string
): Promise<void> {
  const answer = await ask(env, text, convKey);
  await replyText(env, replyToken, truncate(answer, LINE_TEXT_LIMIT));
}

async function replyText(
  env: Env,
  replyToken: string,
  text: string
): Promise<void> {
  const res = await fetch("https://api.line.me/v2/bot/message/reply", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${env.LINE_CHANNEL_ACCESS_TOKEN}`,
    },
    body: JSON.stringify({
      replyToken,
      messages: [{ type: "text", text }],
    }),
  });
  if (!res.ok) {
    console.error(`LINE reply error: ${res.status} ${await res.text()}`);
  }
}

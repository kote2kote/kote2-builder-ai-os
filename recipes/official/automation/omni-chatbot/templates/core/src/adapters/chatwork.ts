// Chatwork アダプター(Webhook)。
// 「自分宛メンション(mention_to_me)」の Webhook を受けて同じルームに返信する。

import type { Context } from "hono";
import { ask, truncate, type Env } from "../brain";
import { isDuplicate } from "../dedupe";
import { fromBase64, hmacSha256Base64, timingSafeEqual } from "../verify";

const CHATWORK_TEXT_LIMIT = 3900;

export async function handleChatwork(
  c: Context<{ Bindings: Env }>
): Promise<Response> {
  const body = await c.req.text();

  // 署名検証: Webhook トークン(base64)をデコードした鍵で body を HMAC → base64 比較
  const signature = c.req.header("x-chatworkwebhooksignature") ?? "";
  const expected = await hmacSha256Base64(
    fromBase64(c.env.CHATWORK_WEBHOOK_TOKEN),
    body
  );
  if (!timingSafeEqual(expected, signature)) {
    return c.text("bad signature", 401);
  }

  const payload = JSON.parse(body);
  const event = payload.webhook_event;
  if (
    payload.webhook_event_type !== "mention_to_me" ||
    !event?.room_id ||
    !event?.body
  ) {
    return c.text("ok");
  }

  // 同じメッセージの再送は処理しない
  if (await isDuplicate(c.env, `chatwork:${event.message_id}`)) {
    return c.text("duplicate");
  }

  // [To:12345] のようなタグ表記を除いて質問文だけにする
  const text = String(event.body)
    .replace(/\[[^\]]*\]/g, "")
    .trim();

  // 合言葉コマンド(EXCL-01)はこのレシピに含めない

  c.executionCtx.waitUntil(
    replyToChatwork(c.env, String(event.room_id), event.from_account_id, text)
  );
  return c.text("ok");
}

async function replyToChatwork(
  env: Env,
  roomId: string,
  fromAccountId: number | undefined,
  text: string
): Promise<void> {
  // 会話の鍵: ルームごとに文脈が続く
  const answer = await ask(env, text, `chatwork:${roomId}`);
  await postToChatwork(env, roomId, fromAccountId, truncate(answer, CHATWORK_TEXT_LIMIT));
}

async function postToChatwork(
  env: Env,
  roomId: string,
  fromAccountId: number | undefined,
  text: string
): Promise<void> {
  const prefix = fromAccountId ? `[To:${fromAccountId}]\n` : "";
  const res = await fetch(
    `https://api.chatwork.com/v2/rooms/${roomId}/messages`,
    {
      method: "POST",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        "x-chatworktoken": env.CHATWORK_API_TOKEN,
      },
      body: new URLSearchParams({
        body: prefix + text,
        self_unread: "0",
      }),
    }
  );
  if (!res.ok) console.error(`Chatwork post error: ${res.status}`);
}

// Slack アダプター(Events API)。
// メンション(@ボット名)と DM に返信する。Socket Mode は OFF にすること(PIT-SLACK-001)。3 秒以内に 200 を返さないと Slack が再送してくるので、
// 先に ACK してから waitUntil の中で考えて返信する。

import type { Context } from "hono";
import { ask, truncate, type Env } from "../brain";
import { isDuplicate } from "../dedupe";
import { hmacSha256Hex, timingSafeEqual } from "../verify";

const SLACK_TEXT_LIMIT = 3900; // 実上限 4000 弱に安全マージン

export async function handleSlack(
  c: Context<{ Bindings: Env }>
): Promise<Response> {
  const body = await c.req.text();

  // 署名検証: v0:{timestamp}:{body} を Signing Secret で HMAC したものが署名と一致するか
  const timestamp = c.req.header("x-slack-request-timestamp") ?? "";
  const signature = c.req.header("x-slack-signature") ?? "";
  if (Math.abs(Date.now() / 1000 - Number(timestamp)) > 60 * 5) {
    return c.text("stale request", 401);
  }
  const expected =
    "v0=" +
    (await hmacSha256Hex(c.env.SLACK_SIGNING_SECRET, `v0:${timestamp}:${body}`));
  if (!timingSafeEqual(expected, signature)) {
    return c.text("bad signature", 401);
  }

  const payload = JSON.parse(body);

  // 初回登録時の URL 確認(Slack が challenge を送ってくる)
  if (payload.type === "url_verification") {
    return c.json({ challenge: payload.challenge });
  }

  if (payload.type === "event_callback") {
    const event = payload.event;

    // 受信イベントの要約ログ(秘密情報は含めない)。二重返信などの切り分けに使う
    console.log(
      `slack event: id=${payload.event_id} type=${event?.type} subtype=${event?.subtype ?? "-"} bot=${event?.bot_id ? "y" : "n"} ch_type=${event?.channel_type ?? "-"} ts=${event?.ts} thread=${event?.thread_ts ?? "-"} retry=${c.req.header("x-slack-retry-num") ?? "0"}`
    );

    // ボット自身の発言・編集イベントには反応しない(無限ループ防止)
    if (event?.bot_id || event?.subtype) return c.text("ok");
    if (event?.type !== "app_mention" && event?.channel_type !== "im") {
      return c.text("ok");
    }

    // 再送された同一イベントは処理しない
    if (await isDuplicate(c.env, `slack:${payload.event_id}`)) {
      return c.text("duplicate");
    }

    const text = String(event.text ?? "")
      .replace(/<@[A-Z0-9]+>/g, "") // メンション表記を除去
      .trim();

    // 合言葉コマンド(EXCL-01)はこのレシピに含めない

    // 会話の鍵: DM は相手との会話ごと、チャンネルはスレッドごとに文脈が続く
    const convKey =
      event.channel_type === "im"
        ? `slack:im:${event.channel}`
        : `slack:${event.channel}:${event.thread_ts ?? event.ts}`;
    c.executionCtx.waitUntil(replyToSlack(c.env, event, text, convKey));
  }

  return c.text("ok"); // ここまで 3 秒以内に返すのが鉄則
}

async function replyToSlack(
  env: Env,
  event: { channel: string; ts: string; thread_ts?: string },
  text: string,
  convKey: string
): Promise<void> {
  const answer = await ask(env, text, convKey);
  await postToSlack(env, event, truncate(answer, SLACK_TEXT_LIMIT));
}

async function postToSlack(
  env: Env,
  event: { channel: string; ts: string; thread_ts?: string },
  text: string
): Promise<void> {
  const res = await fetch("https://slack.com/api/chat.postMessage", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${env.SLACK_BOT_TOKEN}`,
    },
    body: JSON.stringify({
      channel: event.channel,
      thread_ts: event.thread_ts ?? event.ts, // スレッドで返す(チャンネルを散らかさない)
      text,
    }),
  });
  const result = (await res.json()) as { ok: boolean; error?: string };
  if (!result.ok) console.error(`Slack post error: ${result.error}`);
}

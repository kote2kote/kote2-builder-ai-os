// Discord アダプター(Interactions = スラッシュコマンド方式)。
// 通常メッセージの受信には常駐接続(Gateway)が必要なため、Webhook で完結する
// スラッシュコマンド(/ask 質問文)で受ける。コマンド登録手順は docs/channel-setup.html 参照。

import type { Context } from "hono";
import { ask, truncate, type Env } from "../brain";
import { verifyEd25519 } from "../verify";

const DISCORD_TEXT_LIMIT = 2000;

// Interaction types
const PING = 1;
const APPLICATION_COMMAND = 2;

export async function handleDiscord(
  c: Context<{ Bindings: Env }>
): Promise<Response> {
  const body = await c.req.text();

  // 署名検証(Ed25519): timestamp + body に対する署名を公開鍵で確認
  const signature = c.req.header("x-signature-ed25519") ?? "";
  const timestamp = c.req.header("x-signature-timestamp") ?? "";
  const valid = await verifyEd25519(
    c.env.DISCORD_PUBLIC_KEY,
    signature,
    timestamp + body
  );
  if (!valid) return c.text("bad signature", 401);

  const interaction = JSON.parse(body);

  // Discord からの疎通確認
  if (interaction.type === PING) return c.json({ type: 1 });

  if (interaction.type === APPLICATION_COMMAND && interaction.data?.name === "ask") {
    const question = String(
      interaction.data.options?.find(
        (o: { name: string; value?: unknown }) => o.name === "text"
      )?.value ?? ""
    ).trim();

    // 合言葉コマンド(EXCL-01)はこのレシピに含めない

    // まず「考え中…」の仮応答(type 5 = deferred)を 3 秒以内に返し、
    // 本回答は waitUntil の中で元メッセージを書き換える
    // 会話の鍵: チャンネルごとに文脈が続く(同じチャンネルで /ask を続ければ会話になる)
    const convKey = interaction.channel_id
      ? `discord:${interaction.channel_id}`
      : undefined;
    c.executionCtx.waitUntil(
      followUp(c.env, interaction.token, question, convKey)
    );
    return c.json({ type: 5 });
  }

  return c.json({ type: 4, data: { content: "未対応のコマンドです" } });
}

async function followUp(
  env: Env,
  interactionToken: string,
  question: string,
  convKey?: string
): Promise<void> {
  const answer = question
    ? await ask(env, question, convKey)
    : "質問文が空でした。`/ask text:聞きたいこと` の形で送ってください。";
  const res = await fetch(
    `https://discord.com/api/v10/webhooks/${env.DISCORD_APPLICATION_ID}/${interactionToken}/messages/@original`,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content: truncate(answer, DISCORD_TEXT_LIMIT) }),
    }
  );
  if (!res.ok) console.error(`Discord followup error: ${res.status}`);
}

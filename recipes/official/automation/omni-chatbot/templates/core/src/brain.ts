// 共通の頭脳。どのチャネルから来たメッセージも、ここで Claude API に渡して返答文を作る。
// チャネル固有の事情(署名検証・返信 API)はここに持ち込まない。
// ({{PROJECT_NAME}} の CORE-01: AI を呼ぶのはこの 1 箇所だけ)

export interface Env {
  // 頭脳
  ANTHROPIC_API_KEY?: string; // API 直叩きの時だけ必要(ローカル CLI モードでは空で OK)
  CLAUDE_MODEL?: string; // 未設定なら claude-sonnet-5
  BOT_SYSTEM_PROMPT?: string; // ボットの人格・役割(未設定なら汎用アシスタント)
  CODEX_BIN?: string; // codex バイナリの場所(未設定なら PATH → Codex.app 同梱の順で探す)
  CODEX_MODEL?: string; // codex-exec / codex-app 頭脳のモデル(未設定なら codex の内蔵既定)
  CODEX_TIMEOUT_MS?: string; // codex-exec / codex-app の持ち時間(未設定なら 55000 = LINE の返信期限の内側)

  // Slack
  SLACK_BOT_TOKEN: string;
  SLACK_SIGNING_SECRET: string;

  // Discord(スラッシュコマンド方式)
  DISCORD_PUBLIC_KEY: string;
  DISCORD_APPLICATION_ID: string;
  DISCORD_BOT_TOKEN: string;

  // Chatwork
  CHATWORK_API_TOKEN: string;
  CHATWORK_WEBHOOK_TOKEN: string;

  // LINE
  LINE_CHANNEL_SECRET: string;
  LINE_CHANNEL_ACCESS_TOKEN: string;

  // 二重返信ガードの永続化(任意。未設定ならメモリのみで動く)
  DEDUPE_KV?: KVNamespace;
}

export const DEFAULT_SYSTEM_PROMPT =
  "あなたはチャットで質問に答える親切なアシスタントです。" +
  "日本語で、チャットに収まる長さで簡潔に答えてください。";

// 頭脳バックエンドの差し替え口。
// Workers では未設定のまま(下の Claude API 直叩き)。
// PC ローカル実行(server-node.ts)では claude CLI 版(brain-cli.ts)等が注入される。
// Node 専用コードをここに import しないための仕掛け(Workers のバンドルを汚さない)。
//
// convKey(会話の鍵)= 「どの会話の続きか」を表す文字列(例: slack:C123:171234.5678)。
// アダプターが作り、記憶に対応したバックエンドだけが使う(未対応のバックエンドは無視してよい)。
type AskFn = (env: Env, userText: string, convKey?: string) => Promise<string>;
type ForgetFn = (convKey: string) => boolean;
let backendOverride: AskFn | null = null;
let forgetOverride: ForgetFn | null = null;
export function setBrainBackend(fn: AskFn, forget?: ForgetFn): void {
  backendOverride = fn;
  forgetOverride = forget ?? null;
}

// 「忘れて」で会話の記憶をリセットする(記憶対応バックエンドの時だけ反応する)
const RESET_WORDS = new Set(["忘れて", "リセット", "会話リセット"]);

// 合言葉コマンド(EXCL-01)はこのレシピに含めない

/**
 * ユーザーの発言 1 件を Claude に渡して返答文を得る。
 * 失敗時はリトライせず定型文を返す(重複より欠損を選ぶ)。
 * convKey を渡すと、記憶対応バックエンドでは会話の続きとして扱われる。
 */
export async function ask(
  env: Env,
  userText: string,
  convKey?: string
): Promise<string> {
  if (convKey && forgetOverride && RESET_WORDS.has(userText.trim())) {
    const had = forgetOverride(convKey);
    return had
      ? "ここまでの会話をリセットしました。新しい話題からどうぞ。"
      : "覚えている会話はありませんでした。そのまま新しい話題からどうぞ。";
  }
  if (backendOverride) return backendOverride(env, userText, convKey);

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": env.ANTHROPIC_API_KEY ?? "",
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: env.CLAUDE_MODEL || "claude-sonnet-5",
      max_tokens: 1024,
      system: env.BOT_SYSTEM_PROMPT || DEFAULT_SYSTEM_PROMPT,
      messages: [{ role: "user", content: userText }],
    }),
  });

  if (!res.ok) {
    console.error(`Claude API error: ${res.status} ${await res.text()}`);
    return "ごめんなさい、いま頭脳(Claude API)につながりませんでした。少し待ってからもう一度話しかけてください。";
  }

  const data = (await res.json()) as {
    content?: Array<{ type: string; text?: string }>;
  };
  const text = data.content?.find((b) => b.type === "text")?.text;
  return text ?? "(応答が空でした)";
}

/** チャネルごとの文字数上限に合わせて切り詰める */
export function truncate(text: string, limit: number): string {
  return text.length <= limit ? text : text.slice(0, limit - 1) + "…";
}

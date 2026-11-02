# 「MCP とは」解説映像の根拠

確認日: 2026-10-08(MCP の最新プロトコル版は 2026-07-28)。読者: MCP を初めて聞く非エンジニア。

| 映像の説明 | 確認した事実(公式の言い回し) | 出典 |
|---|---|---|
| MCP = AI アプリと道具をつなぐ共通の差し込み口 | "an open-source standard for connecting AI applications to external systems" | [MCP 公式: What is MCP](https://modelcontextprotocol.io/docs/getting-started/intro) |
| 公式のたとえ「AI アプリ版の USB-C」 | "Think of MCP like a USB-C port for AI applications" | 同上 |
| これまでは組み合わせごとに専用のつなぎ込み | 直接の記述は無い。公式の利点 "reduces development time and complexity" "build once and integrate everywhere" からの言い換え(**解釈**)。2 × 3 = 6 は説明用の例 | 同上 |
| ホスト = AI アプリ(Claude Desktop・Claude Code) | "an MCP host — an AI application like Claude Code or Claude Desktop" | [MCP 公式: Architecture](https://modelcontextprotocol.io/docs/learn/architecture) |
| サーバーごとにクライアントを 1 つ | "The MCP host accomplishes this by creating one MCP client for each MCP server" | 同上 |
| サーバーが差し出す 3 種類(道具・資料・定型文) | Tools = "Executable functions … to perform actions" / Resources = "Data sources that provide contextual information" / Prompts = "Reusable templates" | 同上 |
| つなぎ方 2 通り(PC の中 / ネット越し) | Stdio = "local processes on the same machine" / Streamable HTTP = "enables remote server communication" | 同上 |
| つなぐのは信頼できるサーバーだけ | "Verify you trust each server before connecting it." | [Claude Code: MCP](https://code.claude.com/docs/en/mcp) |
| 例: Notion / GitHub / ファイル | 公式の利用例に Notion("access your Google Calendar and Notion")とファイル("local files")。GitHub は説明用の例。各サーバーの機能(ページを読む・書く など)は「例:」と明記 | MCP 公式 intro |

## 矢印

| ID | 起点 | 終点 | 動くもの |
|---|---|---|---|
| w1–w6 | AI アプリ A / B | Notion / GitHub / ファイル | (組み合わせごとの専用接続。説明用) |
| U1 | あなた | ホスト | 頼みごと「議事録をまとめて」 |
| M1–M3 | クライアント | MCP サーバー | MCP でのやりとり(M1 で「ページを読む」) |
| R1 | Notion サーバー | クライアント | ページの中身 |
| U2 | ホスト | あなた | まとめた答え |

## 省いたこと

- JSON-RPC、能力の確認(discovery)、通知、Elicitation、MCP Apps などの拡張 — 初めての人の理解には不要
- 古い接続方式 SSE(Claude Code では非推奨)

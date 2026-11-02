<!-- ============================================================ -->
<!-- recipe-omni-chatbot — マルチチャネル AI チャットボット             -->
<!-- 由来: output/omni-chatbot の実ビルドを結晶化(2026-07-22 生成 →     -->
<!--       2026-08-31 ローカルモードで 4 チャネル実開通)。               -->
<!--       建てる順路(§5)と地雷(§6)は当事者文脈から結晶化。           -->
<!-- 状態: 実ビルドで結晶化済み(ローカルモード運用で 4 チャネル往復緑)。 -->
<!-- ★固有値を焼かない: ドメイン・トークン・実パスはプレースホルダのみ。  -->
<!-- ★除外宣言: 作者環境の「合言葉コマンド(ニュース配信連携)」と         -->
<!--   「送信ハブ(send.mjs)」はこのレシピに含めない(§1 EXCL 参照)。    -->
<!-- v2: 先頭メタ(製品名 / 用途 / 検証 3 軸)は recipe.json へ移動。核の参照実装   -->
<!--   templates/core(署名検証・dedupe・4 アダプター・入口 2 枚・ローカル頭脳 4 枚・  -->
<!--   疎通スクリプト・手順書・Codex 頭脳の設計書)と動作テスト tests/ を同梱          -->
<!--   (2026-09-04 移行。UI は無い = templates/ui / assets/screens / tests/ui なし。   -->
<!--   出所は recipe.json provenance 参照)。                                          -->
<!-- 更新 1.1.0(2026-09-11): ローカル頭脳を 4 方式化(BRAIN_BACKEND = cli / sdk /       -->
<!--   codex-exec / codex-app)+ 会話メモリ(会話キー配管 + 「忘れて」)。生成物側の      -->
<!--   2026-09-05〜09-08 の実ビルド(各方式で実チャネル往復・記憶 4 連・道具遮断を確認)  -->
<!--   を更新モードで昇格。設計 → Codex 実機レビュー(修正後 GO)→ 実装 → テストの順。   -->
<!-- ============================================================ -->

# recipe-omni-chatbot — マルチチャネル AI チャットボット

「Slack / Discord / Chatwork / LINE の 4 チャネルで動く AI チャットボットを、頭脳 1 本 + アダプター方式で一発構築」を再現する設計書(シード)。

- **この設計書の肝**: 頭脳(AI 呼び出し)とチャネル(各サービスの方言)を完全分離するアダプター方式。チャネル追加=アダプター 1 枚 + ルート 1 行。運用形態(ローカル CLI 頭脳 / Workers API 頭脳)は差し替え口 1 つで切り替わる。ローカル頭脳は 4 方式(claude CLI / Agent SDK / Codex exec / Codex App Server)を同じ差し替え口で選び、会話メモリは「配管」と「記憶」の 2 層で持つ。

---

## 1. これは何 / 機能構成 + 完成形(受け入れ基準)

メッセンジャー 4 種のどこから話しかけても、同じ頭脳(Claude)が返事するボット。受け口は Webhook、返信は各チャネルの公式 API。核+アダプタ形(新チャネル = ADAPT 行を 1 つ足す)。

### 機能構成(★ここだけが必須/任意/不採用を決める正本。他章はこの表を参照する)

| ID | 機能 | 状態 | Phase | 完成判定 |
|---|---|---|---|---|
| CORE-01 | 頭脳 1 本 + アダプター方式(AI を呼ぶのは brain 1 箇所だけ) | required | Phase 2 | PASS 必須 |
| CORE-02 | 全チャネルの署名検証(HMAC-SHA256 / Ed25519) | required | Phase 2 | PASS 必須 |
| CORE-03 | 3 秒以内 ACK → 重い処理は waitUntil へ | required | Phase 2 | PASS 必須 |
| CORE-04 | 二重返信ガード(イベント ID の重複弾き + 再送スキップ) | required | Phase 2 | PASS 必須 |
| CORE-05 | 送信出口の一本化(疎通スクリプト経由。AI に curl 直叩きさせない) | required | Phase 2 | PASS 必須 |
| ADAPT-01 | Slack アダプター(メンション + DM。Events API) | optional-enabled | Phase 4 | enabled なら PASS 必須 |
| ADAPT-02 | Discord アダプター(/ask スラッシュコマンド。Interactions) | optional-enabled | Phase 4 | enabled なら PASS 必須 |
| ADAPT-03 | Chatwork アダプター(自分宛メンション) | optional-enabled | Phase 4 | enabled なら PASS 必須 |
| ADAPT-04 | LINE アダプター(トーク返信。Messaging API) | optional-enabled | Phase 4 | enabled なら PASS 必須 |
| FEAT-01 | ローカルモード(PC の Node サーバー + claude CLI 頭脳 + 名前付き Cloudflare Tunnel) | optional-enabled | Phase 3A | enabled なら PASS 必須 |
| FEAT-02 | Workers 本番デプロイ(Claude API 頭脳・従量課金)※実デプロイ未検証(wrangler dev までは緑) | optional-disabled | Phase 3B | 既定 SKIP |
| FEAT-03 | ローカル頭脳の Agent SDK 方式(BRAIN_BACKEND=sdk で CLI 方式と切替。実ビルド検証済み) | optional-disabled | Phase 3A | 既定 SKIP(ON にしたら PASS 必須) |
| FEAT-04 | 会話メモリ(会話キー: Slack=スレッド(DM は相手)/ LINE=相手・グループ / Chatwork=ルーム / Discord=チャンネル。セッション再開・60 分 TTL・「忘れて」でリセット。FEAT-03 / FEAT-05 / FEAT-06 のいずれかが ON の時に効く) | optional-disabled | Phase 3A | 既定 SKIP(記憶対応頭脳と同時に ON) |
| FEAT-05 | ローカル頭脳の Codex exec 方式(BRAIN_BACKEND=codex-exec。ChatGPT プラン内認証・記憶つき・直列キュー + 世代番号。実ビルド検証済み) | optional-disabled | Phase 3A | 既定 SKIP(ON にしたら PASS 必須) |
| FEAT-06 | ローカル頭脳の Codex App Server 常駐方式(BRAIN_BACKEND=codex-app。exec の起動ラグ解消版。道具フラグ名指し全滅 + MCP 起動警報で fail-closed + プロセス/会話の二重世代番号。実ビルド検証済み) | optional-disabled | Phase 3A | 既定 SKIP(ON にしたら PASS 必須) |
| EXCL-01 | 合言葉コマンド(特定の発言で別プロジェクトの自動化を起動。例: ニュース配信) | excluded | — | 別レシピ |
| EXCL-02 | 送信ハブ(他プロジェクトからの送信口スクリプト) | excluded | — | 別レシピ |
| EXCL-03 | 会話履歴の永続化(KV / D1 に保存して再起動をまたぐ。メモリ内の会話メモリは FEAT-04) | excluded | — | 拡張余地(§4 派生) |

### 完成形(受け入れ基準)

- [ ] required の機能がすべて緑
- [ ] enabled な optional がすべて緑(disabled は SKIP=欠落ではない)
- [ ] enabled にしたチャネルすべてで「実メッセージ → AI の返信」の往復が成立 ← ここまでが「完成」

---

## 2. スタック

| 層 | 採用 | 一行理由 |
|---|---|---|
| 言語 | TypeScript | 型で 4 チャネルの payload 差異を安全に吸収 |
| Web フレームワーク | Hono | Workers / Node 両対応。同じアプリを両運用形態で使い回せる |
| ランタイム(ローカル) | Node 22+ + @hono/node-server + tsx | FEAT-01。PC 上で .env 直読みで動かす(recipe.json `runtime` 参照) |
| ランタイム(本番) | Cloudflare Workers(wrangler) | FEAT-02。無料枠サーバーレス |
| 頭脳(ローカル) | claude CLI(プラン内認証)。`BRAIN_BACKEND` で Agent SDK(FEAT-03。`@anthropic-ai/claude-agent-sdk`)/ Codex CLI `codex exec`(FEAT-05。ChatGPT プラン内認証)/ Codex App Server 常駐(FEAT-06)に切替可 | API 従量課金ゼロ。§3-5 の差し替え口で注入。Claude 側はプラン内で動く(2026-09 時点。クレジット制への変更計画は一時停止中 — 買い手は最新の公式案内を確認)。Codex 側は本人限定運用が前提 |
| 頭脳(本番) | Claude API | Workers から fetch 1 本 |
| 公開経路(ローカル) | cloudflared 名前付きトンネル | Webhook を PC に届ける。URL 固定(§6 PIT-CFTUNNEL-001) |
| パッケージ管理 | pnpm | 構築手順は `knowledge/pnpm.md` 参照。allowBuilds に esbuild / workerd / sharp |

---

## 3. 魔法のタネ ★変えるな(崩すと別物になる本質)

1. **頭脳とチャネルの完全分離**: AI を呼ぶのは brain 1 箇所だけ。アダプターは「署名検証 → テキスト抽出 → 返信 API」の変換に徹する。チャネル追加で頭脳や他チャネルに手を入れない
2. **ACK-then-work**: Webhook には 3 秒以内に 200 を返し、AI 呼び出し・返信は waitUntil に逃がす(Slack / LINE は ACK が遅いと同一イベントを再送してくる)
3. **署名検証を絶対に外さない**: 「動かないから一時的にスキップ」を許すとなりすまし放題。デバッグはダミー署名で 401 が返ることの確認から始める
4. **重複より欠損**: 送信は 1 回のみ・失敗してもリトライしない。dedupe(CORE-04)と対で「二重返信ゼロ」を守る
5. **頭脳バックエンドの差し替え口**: brain に setBrainBackend() を置き、ローカル(CLI)/ 本番(API)の切り替えを注入 1 行にする。運用形態の分岐をアダプターに漏らさない
6. **送信出口の一本化**: AI に返信 API を curl 直叩きさせない(過去に二重投稿の実測事故)。出口はスクリプトに封じる
7. **ローカル頭脳の三重ガード**: claude CLI は「道具全禁止 + 空ディレクトリで実行 + --strict-mcp-config でコネクタ(MCP)遮断」。チャネル越しの第三者が運営者の PC・外部サービスに触る経路を全部塞ぐ(§6 PIT-CC-MCP-001)。sdk / codex-exec / codex-app も同じ契約を各方式の流儀に翻訳して守る(Codex は道具フラグの名指し全滅 + MCP 起動警報で fail-closed + 子プロセスの環境変数を最小化 + ボット専用 CODEX_HOME。§6 PIT-CODEX-001)
8. **会話メモリは「配管」と「記憶」の 2 層**: 会話キー(convKey)の配管はバックエンド非依存(ask() に通し、各アダプターが会話単位で鍵を作る)、記憶はバックエンド固有(SDK の resume / Codex の thread)。「忘れて」は brain の 1 箇所で判定して forget 関数に委ねる。記憶を特定の頭脳に閉じ込めない=頭脳を差し替えても配管を作り直さない

---

## 4. 改変の余地 ★変えていい(knob 3 分類)

- **軽量設定**(サイレント適用可): BOT_SYSTEM_PROMPT(ボットの人格)/ CLAUDE_MODEL / CODEX_MODEL・CODEX_TIMEOUT_MS(FEAT-05 / 06)/ ローカルポート(既定 8791)/ トンネルのホスト名 / チャネル別の文字数上限マージン / 会話メモリの TTL(既定 60 分)
- **機能モジュール**(§1 表の状態で ON/OFF): ADAPT-01〜04 の取捨(使うチャネルだけ .env 記入 + Webhook 登録すればよい。コードの削除は不要)/ FEAT-01↔FEAT-02 の運用形態 / FEAT-03 / 05 / 06 ローカル頭脳の方式(`BRAIN_BACKEND=cli|sdk|codex-exec|codex-app`。契約・安全ガードは同一。記憶が要るなら sdk / codex-* + FEAT-04)
- **派生アーキ**(knob ではない。提案 → ユーザー GO で別実装): Discord の常駐 Gateway 化(通常メッセージ受信)/ 会話履歴の永続化(KV / D1。EXCL-03。再起動をまたぐ記憶)/ 合言葉コマンドで別プロジェクト起動(EXCL-01。魔法のタネ §3-7 の三重ガード設計を移植して別途設計する)/ 新チャネル追加(= ADAPT 行 1 つ + アダプター 1 枚 + ルート 1 行)

---

## 5. 再現の順路(Phase + 検証)

- **Phase 0 — 土台**: Node 22+ / pnpm(構築は `knowledge/pnpm.md` 参照)。`pnpm-workspace.yaml` の allowBuilds に esbuild / workerd / **sharp**(§6 PIT-PNPM-001)
  - 検証: `pnpm install` が素通り
- **Phase 1 — 骨格**: package.json(dependencies: `hono` / `@hono/node-server` / `@anthropic-ai/claude-agent-sdk`(FEAT-03 の頭脳。核 `src/brain-sdk.ts` が常に import するので既定 OFF でも入れる。**`^0.3.0` 以上**を指定 — 古い版の範囲を書くと `settingSources` / `strictMcpConfig` / `resume` が無い版に解決されうる。実ビルドは 0.3.263)・devDependencies: `tsx` / `typescript` / `wrangler` / `@cloudflare/workers-types` / `@types/node`・scripts: `dev:local` = `tsx watch src/server-node.ts` / `typecheck` = `tsc --noEmit` / `tunnel:named`)+ tsconfig(`types: ["@cloudflare/workers-types", "node"]`・`moduleResolution: Bundler`)+ wrangler.jsonc(`main: src/index.ts`。秘密は書かない)+ Hono アプリ + `GET /` 生存確認(「`{{PROJECT_NAME}} is running`」の固有文字列を返す。§6 PIT-CFTUNNEL-002 の切り分けに効く)。`GET /` を含む入口は Phase 2 で `templates/core/` からコピーするので、ここでは依存とスクリプトを揃えるだけでよい
  - 検証: `pnpm install` 素通り + `pnpm typecheck` 緑 + curl でトップの本文確認
- **Phase 2 — 核**: **核をゼロから書かない**。まず `recipe.json` の `templates.core[]` に従い、パッケージの `templates/core/` を各 `to` へコピーする(`src/verify.ts`=CORE-02 署名検証の共通道具 / `src/dedupe.ts`=CORE-04 二重返信ガード / `src/brain.ts`=CORE-01 頭脳 1 本 + 差し替え口 / `src/brain-cli.ts`=ローカル頭脳の三重ガード(既定の cli 方式)/ `src/brain-sdk.ts` `src/brain-codex.ts` `src/brain-app.ts`=FEAT-03 / 05 / 06 のローカル頭脳(`src/server-node.ts` が `BRAIN_BACKEND` で 1 つ選ぶ)/ `docs/design-brain-codex.md`=Codex 頭脳 2 枚の設計書(レビュー経緯込み。人間向け)/ `src/index.ts`=Workers 入口 + `/webhook/{channel}` ルーティング / `src/server-node.ts`=Node 入口(FEAT-01)/ `src/adapters/{slack,discord,chatwork,line}.ts`=ADAPT-01〜04 / `send-test.sh`(`scripts/` 配下)=CORE-05 送信出口 / `docs/channel-setup.html`=Phase 4 の手順書)。次に `{{PROJECT_NAME}}` `{{WEBHOOK_BASE_URL}}` を §9 の値で置換し、パッケージの `tests/` を生成物の `recipe-tests/` へ写す。**署名検証(HMAC-SHA256 の対象文字列・Discord の Ed25519・タイムスタンプ 5 分)/ 3 秒 ACK → waitUntil の分割 / dedupe / 各アダプターの request・response の形は散文から再導出すると必ずどこかがズレる**ので、コピーした実装を正とし、買い手の knob(§4 軽量設定)は**コピー後に**当てる。CORE-03(ACK-then-work)はアダプター 4 枚の中に焼き込まれている(`c.executionCtx.waitUntil(...)` の直後に `return`)。作者環境固有の合言葉コマンド分岐(§1 の excluded 項)は `templates/core/` から既に外してある(各ファイルの「このレシピに含めない」コメントが目印)ので、足さない
  - 検証: `bash recipe-tests/smoke-typecheck.sh` 緑(TEST-002)+ `node recipe-tests/webhook-signature.mjs` 緑(TEST-003 / TEST-013: ダミー秘密で `src/server-node.ts` を起動し 4 チャネルの署名検証を機械確認。実チャネル不要)+ `node recipe-tests/dedupe-unit.mjs` 緑(TEST-014)+ `node recipe-tests/brain-backend-unit.mjs` 緑(TEST-019: convKey 配管・「忘れて」・不明な `BRAIN_BACKEND` の fail-fast)。実受信は Phase 4
- **Phase 3A — ローカルモード(FEAT-01)**: Node 入口 `src/server-node.ts`(Phase 2 でコピー済み: `.env` 直読み + CLI 頭脳注入 + 専用ポート既定 8791)+ claude CLI バックエンド `src/brain-cli.ts`(三重ガード §3-7。同じくコピー済み)+ `.env.example`(§9 の環境変数名を空値で列挙)+ 名前付きトンネル(初回セットアップスクリプト `tunnel-named-setup.sh`(`scripts/` 配下)= `cloudflared tunnel login → create → route dns → プロジェクト直下に tunnel.config.yml を書く`(`~/.cloudflared/config.yml` は触らない)→ 以後 `pnpm tunnel:named` の 1 コマンド起動)。**ローカル頭脳は 4 方式とも Phase 2 でコピー済み**で、`.env` の `BRAIN_BACKEND`(既定 `cli`)で選ぶ: **FEAT-03 `sdk`** = `src/brain-sdk.ts`(`@anthropic-ai/claude-agent-sdk` の query() で同じ三重ガード: `allowedTools: []` / `strictMcpConfig: true` + 空 `mcpServers` / `settingSources: []` / systemPrompt 差し替え / 空 cwd。記憶は `resume`)/ **FEAT-05 `codex-exec`** = `src/brain-codex.ts`(`codex exec --json` + `exec resume` で記憶。安全ガードは Codex の流儀に翻訳: 道具は個別キーで全禁止 + read-only サンドボックス(補助)+ 子プロセスの環境変数を最小化(チャネルトークンを渡さない)+ ボット専用 CODEX_HOME(「忘れて」と TTL 失効で `codex delete`)。人格は `developer_instructions`。成功判定 = exit 0 + `turn.completed` + 回答ありの 3 条件。同一会話は直列キュー + 世代番号。タイムアウト既定 55 秒 = LINE replyToken 1 分の内側。§6 PIT-CODEX-002)/ **FEAT-06 `codex-app`** = `src/brain-app.ts`(`codex app-server` を子プロセス 1 本で常駐。改行区切り JSON-RPC: initialize → initialized 通知 → thread/start → turn/start → turn/completed 通知。道具フラグを名指しで全滅 + `--strict-config` + MCP 起動通知で fail-closed(§6 PIT-CODEX-001)+ サーバー発リクエストは拒否応答 + プロセス世代 / 会話世代の二重世代番号 + 受付時からの絶対期限(キュー待ち込み)+ 会話別待機上限・全体同時実行上限 + 死亡時は次の発言で自動再 spawn)。**FEAT-04 会話メモリ**は「配管」(Phase 2 でコピー済み: ask() の convKey と各アダプターの鍵 = Slack はスレッド(DM は相手)/ LINE は相手・グループ / Chatwork はルーム / Discord はチャンネル)+「記憶」(sdk / codex-* の各バックエンドが持つ。60 分 TTL・「忘れて」でリセット)の 2 層で、`cli` では配管だけが動き記憶は無い。不明な `BRAIN_BACKEND` は起動時に fail-fast(黙って既定に落とさない。TEST-019)。**codex-* の運用は本人・許可した利用者に限定**(不特定多数への公開は ChatGPT プラン認証の想定外)。設計と Codex レビューの経緯はコピー済みの `docs/design-brain-codex.md`
  - 検証: `curl http://localhost:{PORT}/` と `curl {{WEBHOOK_BASE_URL}}/` の**本文が両方とも自プロジェクトの固有文字列**(`{{PROJECT_NAME}} is running`)(ステータスコードだけで判定しない)
- **Phase 3B — Workers デプロイ(FEAT-02。既定 OFF・実デプロイ未検証)**: `wrangler deploy` + `wrangler secret put` で本番へ。頭脳は Claude API に切り替わる(注入なしの既定側)
- **Phase 4 — チャネル接続(買い手の管理画面作業)**: 人間向けの詳細手順は Phase 2 でコピーした `docs/channel-setup.html`(スコープ名・`/ask` コマンド登録の JSON・各コンソールのボタン名まで書いてある)。各チャネル共通の順路は「キー発行 → `.env` 記入 → **サーバー再起動(§6 PIT-NODE-002 のワンセットで)** → Webhook URL 登録 → 実メッセージ往復」。チャネル別の要点:
  - ADAPT-01 Slack: Bot User OAuth Token(xoxb で始まる)+ Signing Secret。**Socket Mode を OFF**(§6 PIT-SLACK-001)。URL 検証(challenge)にも署名チェックが掛かるので「.env 記入 → 再起動 → Verify」の順番厳守。イベントは app_mention + message.im
  - ADAPT-02 Discord: Public Key + Application ID + Bot Token。/ask コマンドを API で 1 回登録(commands エンドポイントに POST)→ Interactions Endpoint URL 保存 → bot + applications.commands で招待
  - ADAPT-03 Chatwork: API Token + Webhook トークン(別物)。URL の事前検証なし、イベントは mention_to_me
  - ADAPT-04 LINE: チャネルシークレット + 長期アクセストークン。Webhook 利用 ON + **応答メッセージ(自動応答)OFF**(定型文が二重に返る)
  - 検証: 各チャネルで実返信(TEST-004〜007)+ `node recipe-tests/webhook-signature.mjs --only reject`(TEST-003: 署名なし / 別鍵 / 古いタイムスタンプがすべて 401)

---

## 6. 固有の地雷 + 直し方

1. **[PIT-CFTUNNEL-001] quick tunnel(trycloudflare)が edge 404 で使えない**
   症状: トンネル登録は成功するのに公開 URL が Cloudflare edge の 404(cloudflared にリクエストが届かない)。原因: trycloudflare 側のルーティング不調(作り直し・cloudflared 更新でも再現)。直し方: **名前付きトンネル**を使う(自分のドメインのサブドメインを張る = `{{WEBHOOK_BASE_URL}}` のホスト部分)。URL が固定になり Webhook 登録にも都合が良い。切り分けは `dig @1.1.1.1`(ローカル DNS が引けないことがある)
   確認環境: mac cloudflared 2026.7(2026-07)/ 回帰: TEST-008
2. **[PIT-CFTUNNEL-002] トンネルは 200 なのに応答の中身が別プロジェクト**
   症状: 公開 URL が 200 を返すのに Webhook が届かない。GET / の本文を見ると**別プロジェクトの画面**。原因: トンネルの向き先ポートを他プロジェクト(wrangler dev 等)が localhost で先取りしていた。トンネル自体は正常なので気づきにくい。直し方: このボット専用のポート(既定 8791。wrangler 常用域 8787/8788 を避ける)に統一し、疎通確認は**必ず本文の固有文字列まで見る**(ステータスコードで判定しない)
   確認環境: mac(2026-08)/ 回帰: TEST-008
3. **[PIT-NODE-002] .env 更新後の再起動が「ポート使用中」で静かに失敗**
   症状: 再起動したはずなのに新しい .env の値が反映されない(Slack の URL 検証が 401 のまま等)。原因: 旧プロセスがポートに居座り、新プロセスが EADDRINUSE で即死。バックグラウンド起動だと失敗に気づかない(pkill のパターン照合も外れることがある)。直し方: 再起動は「`lsof -iTCP:{PORT} -sTCP:LISTEN` で PID 特定 → kill → 空き確認 → 起動 → `curl http://localhost:{PORT}/` で応答確認」のワンセットで行う
   確認環境: mac Node 25(2026-08)/ 回帰: TEST-001
4. **[PIT-SLACK-001] Request URL が Verified ✓ なのにイベントが届かない**
   症状: Event Subscriptions は Verified ✓、スコープ・bot events も正しいのにメンションが届かない。原因: **Socket Mode が ON**(ON だとイベントは WebSocket 側に流れ、Request URL には一切配信されない)。新しいアプリ作成画面のテンプレ選択によっては最初から ON。直し方: 左メニュー Socket Mode → OFF。Event Subscriptions ページの「Socket Mode is enabled」の注意書きを最初に見る癖をつける
   確認環境: Slack 新 UI(2026-08)/ 回帰: 手動(Socket Mode トグルの目視)
5. **[PIT-CC-MCP-001] ローカル頭脳(claude CLI)が運営者のコネクタ情報を口走る**
   症状: ボットの返答に運営者の接続サービス(コネクタ)名や認証状態が混ざる。原因: claude CLI が実行アカウントのグローバル設定(MCP コネクタ)を引き継いで起動する。道具の禁止リストだけではコネクタ経由の道具が漏れる=第三者が運営者の外部サービスに触れる経路になり得る。直し方: CLI 起動引数に `--strict-mcp-config` + 空の `--mcp-config`(`{"mcpServers":{}}`)を付け、コネクタを一切読み込ませない
   確認環境: mac claude CLI(2026-08)/ 回帰: 手動(ボットに雑談で話しかけ、返答に運営者環境の情報が出ないこと)
6. **[PIT-PNPM-001] pnpm の ignored-builds → exit 1**(既存 PIT の本レシピでの現れ方)
   症状: 初回 `pnpm install` が `Ignored build scripts: sharp` で exit 1。原因: wrangler 4.112+ が sharp を連れてくるようになり、esbuild / workerd だけの allowBuilds では足りない。直し方: `pnpm-workspace.yaml` の allowBuilds に `sharp: true` を追加。再発したら `node_modules/.modules.yaml` を消してから `pnpm install`(ignored 判定が sticky に残る)。共通知は `knowledge/pnpm.md`
   確認環境: mac pnpm 11(2026-07)/ 回帰: TEST-002
7. **[PIT-PNPM-002] 非対話実行で pnpm が modules purge を確認できず abort**
   症状: バックグラウンド・CI 等の TTY なし実行で `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`(スクリプト実行前の自動 install が node_modules 入れ直しの確認を出せない)。直し方: 一度 `CI=true pnpm install` を前面で実行してから本命コマンドを起動(または `confirmModulesPurge: false`)
   確認環境: mac pnpm 11(2026-08)/ 回帰: 手動(TTY なしで dev 起動が素通りすること)
8. **[PIT-CODEX-001] Codex の道具遮断は「個別キーで全部切れる」前提が不正確(app-server が既定で MCP サーバーを自動起動)**
   症状: `codex app-server` を素の設定で spawn すると、道具を切ったつもりでも `codex_apps` などの MCP サーバーが起動してくる(実測)。exec 方式の 8 キー(approval_policy / shell_tool / web_search / apps / plugins / hooks / multi_agent / memories)だけでは足りない。原因: Codex は道具系の機能フラグが多く、版ごとに増える。直し方: `codex features list` の**実機一覧から道具系フラグを名指しで全滅**(`-c features.{名前}=false` を列挙)+ `--strict-config` でキー名の打ち間違いを起動時に検出 + **MCP 起動通知(`mcpServer/startupStatus/updated`)を遮断失敗の警報**にして fail-closed(以後の発言は定型文で断り、ログに残す)。サーバー発リクエスト(承認・入力要求)も来たら拒否応答 + 警報。Codex を版上げしたら `codex features list` を見直す
   確認環境: mac codex-cli 0.153.4(2026-09)/ 回帰: TEST-018(起動ログに警報ゼロ)
9. **[PIT-CODEX-002] `codex exec resume` がフラグの再指定を受け付けず、安全引数が再開側で落ちる**
   症状: `codex exec resume {id} --sandbox read-only ...` が `unexpected argument`。作成時の設定を引き継ぐ保証も無く、再開時だけ道具制限が緩む穴になる。直し方: **フラグ前置き構文** `codex exec {安全引数} resume {id} --json -` で、新規・再開とも同じ引数生成関数から毎回すべて付ける(resume 側での省略はしない)。発言は標準入力(`-`)で渡し、引数に載せてフラグと誤認させない。成功判定は exit 0 + `turn.completed` + 回答ありの 3 条件(途中発言を完成扱いしない)。resume に失敗した対応は外して次回は新規会話から
   確認環境: mac codex-cli 0.153.4(2026-09)/ 回帰: TEST-017

---

## 7. 固有スキル / 道具

- **channel-verify スキル**: 「疎通テストして」で 4 チャネルの接続状態を順に確認する順路 + このプロジェクトのハマりどころ蓄積場所
- **docs/channel-setup.html**: 4 チャネルの管理画面作業の手順書(人間向け。§5 Phase 4 の詳細版)。`templates/core/docs/channel-setup.html` からコピー
- **疎通スクリプト `send-test.sh`(`scripts/` 配下)**: 短文の送信テスト用の唯一の出口(CORE-05)。`templates/core/` の同名ファイルからコピー
- **ローカル頭脳 4 枚(`src/brain-cli.ts` / `src/brain-sdk.ts` / `src/brain-codex.ts` / `src/brain-app.ts`)**: `BRAIN_BACKEND` で 1 つ選ぶ。`templates/core/` からコピー。Codex 2 枚の設計書 `docs/design-brain-codex.md`(レビュー経緯込み)も同梱
- **recipe-tests/**(パッケージの `tests/` の写し): `smoke-typecheck.sh` / `webhook-signature.mjs`(ダミー秘密 + 実行時生成の Ed25519 鍵で 4 チャネルの署名検証を機械確認)/ `dedupe-unit.mjs` / `brain-backend-unit.mjs`(convKey 配管・「忘れて」・不明な `BRAIN_BACKEND` の fail-fast)/ `fixtures/`(架空の payload と env)

## 8. ハーネス宣言

`templates/` の自動化・連携用途の標準一式(CLAUDE.md 作業指示書 / output-style / rules: secrets・context-hygiene / .project-memory / dashboard)+ 固有上書き: channel-verify スキル、docs/channel-setup.html。

## 9. 適応指示(環境差・安全側・固有値)

- **安全側デフォルト**: 署名検証は常に ON(§3-3)/ 秘密情報はチャットに貼らせず買い手本人が .env に記入(値の有無・文字数だけ機械確認する)/ デプロイ・公開作業は必ず買い手の承認後
- **ログイン前提(ローカル頭脳)**: すべて**買い手自身のアカウント・プラン**で動く。cli / sdk は買い手の PC で `claude login` 済みであること(買い手の Claude プランを消費)、codex-exec / codex-app は `codex login` 済みであること(買い手の ChatGPT プランを消費。初回起動時に `~/.codex/auth.json` をボット専用 CODEX_HOME へコピーするだけで中身は読まない)。作者の認証情報・利用枠はレシピに含まれず、一切使われない
- **テンプレのプレースホルダ(`{{NAME}}`。`recipe.json` の `placeholders` と同じ集合。コピー時に置換)**:

| プレースホルダ | どこに出るか | 値 |
|---|---|---|
| `{{PROJECT_NAME}}` | `src/index.ts`(`GET /` の固有文字列)/ `src/server-node.ts`(起動ログ)/ `src/brain-cli.ts` `src/brain-sdk.ts` `src/brain-codex.ts` `src/brain-app.ts`(一時ディレクトリ名・ボット専用 CODEX_HOME `~/.codex-{{PROJECT_NAME}}`・App Server の clientInfo と拒否応答の文言)/ `send-test.sh`(既定メッセージ)/ `docs/channel-setup.html`(表題)/ `docs/design-brain-codex.md`(本文) | 生成プロジェクトのスラッグ(例: フォルダ名。英数字とハイフン) |
| `{{WEBHOOK_BASE_URL}}` | `docs/channel-setup.html`(各チャネルの Webhook URL の土台) | FEAT-01 なら名前付きトンネルの `https://{買い手の所有ドメインのサブドメイン}` / FEAT-02 なら `https://{name}.{account}.workers.dev` |

- **環境変数(名前だけ書く。値は買い手に聞く or 買い手が発行し、買い手本人が `.env` に記入)**:

| 環境変数 | 入手先 |
|---|---|
| SLACK_BOT_TOKEN / SLACK_SIGNING_SECRET | 買い手の Slack App(api.slack.com/apps) |
| DISCORD_PUBLIC_KEY / DISCORD_APPLICATION_ID / DISCORD_BOT_TOKEN | 買い手の Discord Developer Portal |
| CHATWORK_API_TOKEN / CHATWORK_WEBHOOK_TOKEN | 買い手の Chatwork サービス連携画面 |
| LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN | 買い手の LINE Developers コンソール |
| トンネルのホスト名(`{{WEBHOOK_BASE_URL}}` のホスト部分。`tunnel-named-setup.sh` の引数) | 買い手の所有ドメインのサブドメイン(FEAT-01 のみ) |
| ANTHROPIC_API_KEY | 買い手の Anthropic Console(FEAT-02 のみ。FEAT-01 では不要) |
| BOT_SYSTEM_PROMPT(ボットの人格) | 買い手の業種に合わせて記入(空なら汎用アシスタント) |
| BRAIN_BACKEND(ローカル頭脳の方式) | `cli`(既定)/ `sdk`(FEAT-03)/ `codex-exec`(FEAT-05)/ `codex-app`(FEAT-06)。それ以外は起動時に止まる |
| CODEX_BIN / CODEX_MODEL / CODEX_TIMEOUT_MS | FEAT-05 / 06 のみ。バイナリの場所(未設定なら PATH → Codex.app 同梱の順で自動探索)/ モデル(未設定なら codex の内蔵既定)/ 持ち時間 ms(既定 55000) |

- **Windows 適応(未検証)**: FEAT-01 のローカル運用は mac で検証。Windows では lsof 系の切り分けコマンド(§6 PIT-NODE-002)を netstat 等に読み替える

## 10. 完成判定(買い手の AI が自己検証)

§1 機能構成表に対し:
- required = すべて PASS(1 つでも FAIL なら未完成)
- optional-enabled = enabled のものは PASS / disabled にしたものは SKIP
- optional-disabled = 既定 SKIP(ON にしたなら PASS)
かつ §5 各 Phase の検証が緑。

| TEST ID | 対象 | 種別 | tier | 検証方法 | 期待値 |
|---|---|---|---|---|---|
| TEST-001 | FEAT-01 | auto | full | `curl -fsS -o /dev/null "http://localhost:${PORT:-8791}/"` | トップ 200(`pnpm dev:local` を起動した状態で実行。生成直後のスモークでは走らせない) |
| TEST-002 | — | auto | smoke | `bash recipe-tests/smoke-typecheck.sh` | 型エラー 0(`pnpm typecheck` を包む) |
| TEST-003 | CORE-02 | auto | smoke | `node recipe-tests/webhook-signature.mjs --only reject` | 4 チャネルとも「署名ヘッダなし」「別鍵で署名」が 401。Slack は正しい鍵でもタイムスタンプ 10 分前なら 401(replay 対策)。9 ケース全 PASS |
| TEST-004 | ADAPT-01 | manual | full | Slack でボット宛メンション | AI の返信がスレッドに届く |
| TEST-005 | ADAPT-02 | manual | full | Discord で `/ask text:こんにちは` | 「考え中」→ 本回答に置き換わる |
| TEST-006 | ADAPT-03 | manual | full | Chatwork でボット宛 To メッセージ | AI の返信が届く |
| TEST-007 | ADAPT-04 | manual | full | LINE のトークで話しかける | AI の返信が届く |
| TEST-008 | PIT-CFTUNNEL-002 | manual | full | `curl {{WEBHOOK_BASE_URL}}/` の本文を目視 | 自プロジェクトの固有文字列 `{{PROJECT_NAME}} is running`(200 だけで判定しない) |
| TEST-009 | CORE-04 | manual | full | 同一イベントの再送(Slack の遅延 ACK 等で誘発) | 返信は 1 回のみ |
| TEST-010 | CORE-01 | manual | full | アダプター層に AI 呼び出しが無いことを grep で確認 | 頭脳の呼び出しは brain の 1 箇所のみ |
| TEST-011 | CORE-03 | manual | full | 回答に時間がかかる質問を送り、ACK と返信の分離を観察 | 受信側にタイムアウト表示が出ず、返信は後から届く |
| TEST-012 | CORE-05 | manual | full | 送信経路の棚卸し(スクリプト以外に返信 API を叩く場所が無いこと) | 出口は疎通スクリプトとアダプター内の返信処理のみ |
| TEST-013 | CORE-02 | auto | smoke | `node recipe-tests/webhook-signature.mjs --only accept` | 正しく署名した fixtures が 200(Slack url_verification は challenge を返す / Discord PING は `{type:1}` / Chatwork・LINE は頭脳より手前で ok)。4 ケース全 PASS |
| TEST-014 | CORE-04 | auto | smoke | `node recipe-tests/dedupe-unit.mjs` | `isDuplicate` が同一 ID の 2 回目以降で true・別 ID で false・DEDUPE_KV があれば put(expirationTtl 付き)し、KV に残る ID はメモリが空でも true。7 ケース全 PASS |
| TEST-015 | FEAT-03 | manual | full | `BRAIN_BACKEND=sdk` で再起動 → 実メッセージ送信 → `cli` に戻して再度送信 | どちらの頭脳でも返信が届く(切替が往復できる) |
| TEST-016 | FEAT-04 | manual | full | 同じ会話単位で「◯◯を覚えて」→「◯◯は何?」→「忘れて」→「◯◯は何?」の 4 連(sdk / codex-exec / codex-app のいずれかで) | 2 問目は思い出す・リセット後は知らないと答える |
| TEST-017 | FEAT-05 | manual | full | `BRAIN_BACKEND=codex-exec` で記憶 4 連(覚えて→思い出す→忘れて→知らない)+ 道具遮断(ファイル一覧・環境変数の値を要求)+ 同一会話へ同時 2 発 | 記憶 4 連合格・道具と秘密は「答えられません」・同時 2 発は順に処理され両方に返答 |
| TEST-018 | FEAT-06 | manual | full | `BRAIN_BACKEND=codex-app` で記憶 4 連 + 道具遮断・秘密要求 + 実行中の「忘れて」(1 発目実行中にリセット → 待機中の 2 発目の扱いを見る)+ 起動ログに MCP 警報が無いこと | 記憶・遮断とも合格・待機中の発言は「送り直して」で保護・警報ゼロ(= 道具遮断が実効) |
| TEST-019 | FEAT-04 | auto | smoke | `node recipe-tests/brain-backend-unit.mjs` | 偽の頭脳を注入し、convKey がそのまま渡る・「忘れて」は forget 登録済みの頭脳でだけ横取り(記憶あり / なしで定型文が分かれる)・forget 未登録(cli)では普通の発言として通る。`BRAIN_BACKEND=不明な値` で `src/server-node.ts` が exit 1 + 案内文(黙って既定に落ちない)。6 ケース全 PASS |

テストの約束: `recipe-tests/*.mjs` は `node:` 組み込みだけで動く(新しい依存なし)。`webhook-signature.mjs` は `recipe-tests/fixtures/env.test.json` のダミー秘密と実行時に生成した Ed25519 鍵で `src/server-node.ts` を空きポートに起動し、署名検証の直後に応答が確定する payload だけを POST する(外部サービスにも Claude にもつながらない。10 秒で起動しなければ FAIL)。署名検証の期待値は **401**(`src/verify.ts` の道具を使う各アダプターが `bad signature` / `stale request` を 401 で返す実装。403 ではない)。TEST-003 と TEST-013 は同じスクリプトの `--only reject` / `--only accept`(引数なしで両方)。`dedupe-unit.mjs` は生成物の devDependency `tsx` の ESM API で `src/dedupe.ts` を読む。`brain-backend-unit.mjs` も同じ方法で `src/brain.ts` に偽の頭脳を注入し(Claude / Codex は一度も呼ばれない)、fail-fast の確認だけ `src/server-node.ts` を `BRAIN_BACKEND=不明な値` で起動して終了コードを見る(20 秒で終了しなければ FAIL)。

核(`templates/core/`)以外 — package.json / tsconfig / wrangler.jsonc / `.env.example` / トンネルの初回セットアップスクリプト / ハーネス一式 — は §5 の順路 + `knowledge/pnpm.md` + AI の一般知識から建てる(シード型)。**署名検証・dedupe・頭脳(brain + ローカル頭脳 4 枚)・アダプター 4 枚・入口 2 枚・疎通スクリプト・手順書・Codex 設計書は結晶化で昇格した参照実装が正本**で、コピーしてから配線する。再生の最中に `output/` を読まない(builder.md ⑥。読んでよいのはこのパッケージ内 + `knowledge/` + ビルダー `templates/`)。

<!-- ============================================================ -->
<!-- ai-search-knowledge/RECIPE.md — AI Search ナレッジ(Dify ライク RAG)の共有レシピ(パッケージ v2) -->
<!-- 由来: output/ai-search-knowledge の実ビルド(2026-08-29〜30)からのライブ捕捉 → 結晶化。 -->
<!--       Win 再現ビルド(2026-08-31〜09-01)の学びを逆輸入(CLI 作成 / 同期パス新形式 /     -->
<!--       ai_search バインディング統一 / 4MB 判定の PDF 除外 / 画面導線・デザイン仕様確定)。 -->
<!-- 状態: 実ビルドで required + optional-enabled を建てて全 Phase の緑を確認済み          -->
<!--       2026-09-16〜17 mac 講座版(pro 再生)の実運用から §6 PIT-AISEARCH-011〜013 / PIT-WRANGLER-004 と TEST-024 を追記(1.3.2) -->
<!--       2026-09-21 同じ講座版の実運用で「API は説明を受けるのに画面に入力欄が無い」穴を発見 → FEAT-04(説明欄)+ TEST-025 を UI 参照実装(index / docs / styles)ごと昇格(1.4.0) -->
<!-- v2: 先頭メタ(製品名 / 用途 / 検証 3 軸)は recipe.json へ移動。UI 参照実装 templates/ui・スクショ assets/screens・ -->
<!--     動作テスト tests/ を同梱(2026-09-04 移行。UI は mac 2026-08-30 版 = §5 画面仕様より古い。recipe.json provenance 参照) -->
<!-- ★固有値を焼かない: ドメイン / 実パス / 氏名 / メール / API キー / アカウント ID の    -->
<!--   実値はこのレシピに書かない。買い手ごとに変わる値は §9 の置換表に従う。              -->
<!-- ============================================================ -->

# ai-search-knowledge — Cloudflare AI Search で作る Dify ライクなナレッジ RAG


## 1. これは何 / 機能構成 + 完成形(受け入れ基準)

画面からナレッジ(資料グループ)を作り、PDF / Word / Excel / 画像を放り込むと、チャンク分割・埋め込み・ハイブリッド検索・rerank・回答生成を **Cloudflare AI Search(旧 AutoRAG)が全部やる** RAG システム。回答にはヒット資料一覧(match% 付き)と **PDF ページのサムネイル根拠**が付く。外部 API キー不要・Cloudflare 完結。Dify のナレッジ機能を「1 インスタンス + R2 フォルダ」で再現するのが芯。

### 機能構成(★ここだけが必須/任意/不採用を決める正本)

| ID | 機能 | 状態 | Phase | 完成判定 |
|---|---|---|---|---|
| CORE-01 | ナレッジ = R2 フォルダ(インスタンスは 1 個。チャットは新形 `{folder:"{kb}/"}` フィルタでスコープ、無指定 = 全体横断) | required | Phase 3 | PASS 必須 |
| CORE-02 | PDF は 1 ページ = 1 ファイルでブラウザ分解(pdf.js + CMap)し、ファイル名にページ番号を焼いて逆引き(pageKey 契約)→ ページ根拠サムネイル | required | Phase 4 | PASS 必須 |
| CORE-03 | 台帳(Workers KV)が一覧・削除の正。UI は楽観更新(KV の結果整合を吸収) | required | Phase 3 | PASS 必須 |
| CORE-04 | 即時同期: アップロード・削除のたびに REST(`ai-search`)で同期ジョブを蹴る(30 秒 1 回のレート制限は握って良い) | required | Phase 5 | PASS 必須 |
| CORE-05 | 4MB/ファイル上限は **PDF 以外(非分割ファイル)** の入口(UI + API)で弾く(超過はサイレントに索引されないため)。**PDF は元ファイル全体に掛けない**(ページ分解後に画像ページ単位で判定。13.5MB の PDF も各ページが 4MB 以下なら登録できる) | required | Phase 3 | PASS 必須 |
| FEAT-01 | 文字が取れないスキャンページはページ画像を R2 へ入れ、AI Search の画像索引(image-to-text)に読ませる | optional-enabled | Phase 4 | enabled なら PASS 必須 |
| FEAT-02 | 索引の同期ステータス表示(`GET /api/sync/status`。実行中は 10 秒ポーリング) | optional-enabled | Phase 5 | enabled なら PASS 必須 |
| FEAT-03 | 共通サイドバーシェル + 3 画面導線(ナレッジ一覧 → 資料一覧 → 個別チャット CTA → チャット。§5「画面仕様」が正) | optional-enabled | Phase 6 | enabled なら PASS 必須 |
| FEAT-04 | ナレッジの「説明」を画面で書ける・直せる・一覧で見える(作成フォームの任意欄 / カードに 2 行まで表示 / 資料一覧の見出し下でインライン編集)。台帳の `description` は元から API(`POST /api/kb` / `PATCH /api/kb/:kb`)が受けていたのに画面が無かった穴(2026-09-21)。全体チャットで「どのナレッジを見るか」の手がかり(agentic 派生ではルーティングの判断材料) | optional-enabled | Phase 6 | enabled なら PASS 必須 |
| EXCL-01 | ログイン(Cloudflare Access)/ ナレッジ単位の閲覧権限 | excluded | — | 実務拡張レシピへ |
| EXCL-02 | フォルダ整理(ナレッジのグループ化・フォルダ内横断チャット) | excluded | — | 実務拡張レシピへ |
| EXCL-03 | 音声・動画のタイムスタンプ検索 / スキャン PDF の高精度 OCR | excluded | — | 実務拡張レシピへ |

### 完成形(受け入れ基準)

- [ ] required の機能がすべて緑
- [ ] enabled な optional がすべて緑(disabled は SKIP = 欠落ではない)
- [ ] ローカル(`wrangler dev --remote`)で上が動く ← ここまでが「完成」。公開(deploy)は §9 の合図から

## 2. スタック

| 層 | 採用 | 備考 |
|---|---|---|
| 実行基盤 | Cloudflare Workers + Hono(TypeScript) | ルーター 1 ファイル + 機能別モジュール。構築は `knowledge/cloudflare-workers.md` 参照 |
| 検索・回答 | Cloudflare AI Search(旧 AutoRAG)**専用 `ai_search` バインディング + `chatCompletions()` 経由に統一**(§6 PIT-AISEARCH-006。dev も `remote: true` で本物を参照) | チャンク・埋め込み・ハイブリッド検索・rerank・回答生成を全部委譲(手作り RAG との対比が教材の芯) |
| 文書ストア | R2(AI Search のデータソース) | フォルダ = ナレッジ |
| 台帳・ページ画像 | Workers KV | ナレッジ/資料のメタ + サムネイル。結果整合(§6 PIT-KV-001) |
| 回答生成モデル | Workers AI(既定 `@cf/meta/llama-3.3-70b-instruct-fp8-fast`) | `wrangler.jsonc` の `GEN_MODEL` で差し替え可 |
| 画面 | 素の HTML/CSS/JS(ビルドなし ES モジュール) | pdf.js は CDN 動的ロード(バージョン固定 + CMap 必須) |
| パッケージ管理 | pnpm | `knowledge/pnpm.md` 参照 |

## 3. 魔法のタネ ★変えるな

1. **ナレッジ = ストレージのフォルダ、検索インスタンスは 1 個**。ナレッジ作成をダッシュボード作業にしない(Dify らしさ = 画面から秒で作れること)。スコープはフィルタ、全体横断はフィルタ無し
2. **ページ根拠は「ファイル名にページ番号を焼く」逆引き契約**。検索エンジンは「どのファイル由来か」しか教えない前提で、1 ページ = 1 ファイル(`{kb}/{doc}__pNNNN.md`)にして後から復元する。おまけに 1 ファイル上限も回避できる
3. **台帳が正、索引は追いつく**。一覧・削除の即時性は台帳(KV)+ 楽観更新 UI が担い、検索への反映は同期ジョブに任せて時差を許容する(「削除したのに数分は検索に出る」は仕様として UI 文言で伝える)
4. **上限・失敗は入口で弾く**(非対応形式・PDF 以外の 4MB 超過)。サイレント失敗する層に流し込む前に UI と API の両方で止める。ただし **PDF に元ファイル全体の 4MB 判定を掛けない**(ページ分解が上限回避そのものなので、判定は分解後のページ単位。一律ガードにすると分解で救える PDF まで弾く)
5. **不在は不在と答える**(システムプロンプトで「資料に無いことは推測しない」を固定)。検索が当たっても根拠が薄ければ正直に「記載がありません」

## 4. 改変の余地 ★変えていい

- **軽量設定**: 配色テーマ(kote2 標準テーマの CSS カスタムプロパティ)/ 画面のプロダクト名 `{{PRODUCT_NAME}}`(§9)/ 回答モデル `GEN_MODEL` / バケット・インスタンス名(§9 の対応を揃えること)/ 検索の `max_num_results`(既定 8)
- **機能モジュール**: §1 表の FEAT-01〜04(画像索引 / 同期ステータス / サイドバー UI / 説明欄)。OFF にすると対応 Phase とテストが SKIP になる
- **派生アーキ**: 検索基盤を Vectorize + 手作りパイプラインに置き換える等は knob ではない(§3 の 1〜2 を移植した別レシピ。実例: kaden-manual-rag 系)

## 5. 再現の順路(Phase + 検証)

- **Phase 0 — 土台**: Node 20+ / pnpm / `wrangler login`。手順は `knowledge/pnpm.md`・`knowledge/cloudflare-workers.md` を参照。検証 = `pnpm wrangler whoami` がアカウントを表示
- **Phase 1 — リソース作成**: R2 バケットと KV namespace を wrangler で作成し、KV の id を `wrangler.jsonc` に貼る。**セットアップスクリプトは `templates/core/scripts/setup-cloudflare.sh` を生成物の scripts 直下(`setup-cloudflare.sh`)へコピーして使う(散文から再導出しない。2026-09-07 の Win 再生では文章どおりに書けず `kv namespace create REGISTRY` が出て旧 KV と衝突した = §6 PIT-SETUP-KV-001)**。参照実装の順序 — (a) `wrangler.jsonc` を**字句解析して**読む(改行・キー順・コメント・末尾カンマに依存しない。2026-09-07 Codex: 同じ内容を複数行 JSON に整形しただけで旧版は KV id を書けず作成後に止まった)。名前の整合(`name` / `vars.INSTANCE_NAME` / `bucket_name` = `{name}-docs` / `instance_name` = `{name}` の 4 か所が同じ名前から派生。崩れていれば止まる)+ `kv_namespaces` の binding `REGISTRY` に id を書ける形か**作成前に予行**(書けない形なら CLI を呼ばずに止まる)→ (b) ログイン確認 → (c) **3 種すべてを事前照会**(バケット一覧 / KV 一覧(title `{project}-REGISTRY`。作成も検索も同じ title)/ インスタンス一覧。一覧の取得失敗・**解釈失敗は非ゼロ終了で、「既存なし」に倒さない**: R2 は `wrangler r2 bucket list` のテキスト出力で「Listing buckets」見出しも `name:` 行も無ければ想定外(見出しだけなら空一覧)/ KV は JSON 配列でない・同名 title の要素に 32 桁 16 進の id が無い → 失敗 / AI Search は `ai-search list --json` の配列でない → 失敗)→ (d) 同名が 1 つでもあれば**何も作らず・書き換えずに止まる**(黙って再利用しない。意図して引き継ぐ時だけ `--reuse`。§6 PIT-MULTIBUILD-001)→ (e) 無いものだけ作成(各作成の失敗・KV id の読取失敗は非ゼロ終了)→ (f) **最後に 1 回だけ** KV id を書き込む(コメント・整形は保持し、書いた後に読み直して照合)。同一アカウントに別の生成物(別マシン・別の版)が居るなら 4 か所を同じ接尾辞で揃えてから実行する(§9)。検証 = `wrangler.jsonc` にプレースホルダが残っていない + TEST-022
- **Phase 2 — AI Search インスタンス**: **CLI 作成が正**(2026-08-31 Win 実機確定): `wrangler ai-search create {name} --type r2 --source {bucket} --hybrid-search true`(open beta)。`wrangler login` 済みなら別途トークン不要・ダッシュボード不要で、作成時に hybrid を有効化できるため §6 PIT-AISEARCH-002 も踏まない。名前 = `wrangler.jsonc` の `instance_name` と一致させ、作成後に同期ジョブを 1 回蹴る。ダッシュボード作成はフォールバック(その場合は作成後に `wrangler ai-search update {name} --hybrid-search true` → 同期 1 回)。検証 = `wrangler ai-search list` に表示され `index_method` に keyword が立つ
- **Phase 3 — アプリ本体(CORE-01 / CORE-03 / CORE-05)**: Hono ルーター(`/api/kb` CRUD / `/api/chat` / `/api/sync`)+ 台帳モジュール + 検索モジュール(新形フィルタ)+ 画面 3 枚。ID 生成は非 ASCII 名なら常にハッシュ(§6 PIT-SLUG-001)。検証 = `pnpm typecheck` 緑 + `pnpm dev` でナレッジ作成 → 一覧反映(リロード不要)
- **Phase 4 — PDF ページ分解とページ根拠(CORE-02 / FEAT-01)**: ブラウザ側 pdf.js(**CMap 指定必須** §6 PIT-PDFJS-001)で 1 ページずつテキスト抽出(空白除去後 20 文字閾値)+ ページ画像化。テキストページは `.md`、スキャンページは `.jpg` を R2 へ、サムネイルは KV へ。画像は 2 系統: **根拠表示用(全ページ)は横幅約 1980px・JPEG 品質 0.9**(拡大表示に耐える解像度を優先)、**スキャンページの検索投入用は横幅約 1400px・品質 0.85**。高解像度化は新規登録分から有効(登録済みの低解像度画像は自動再生成されないため、必要なら原本を再登録)。検証 = テキスト PDF を投入 → 同期 → 質問で該当ページのサムネイル + sources が返る
- **Phase 5 — 即時同期(CORE-04 / FEAT-02)**: REST でジョブ作成。パスは**名前空間入りの新形式** `POST /accounts/{account}/ai-search/namespaces/{ns}/instances/{name}/jobs`(§6 PIT-AISEARCH-001。旧 `PATCH .../ai-search/instances/{name}/sync` は 404 化済み)。環境変数名は `SYNC_` 接頭辞(§6 PIT-WRANGLER-003)。429 は「直前の同期に相乗り」として握る。同期トークン未設定でも `pnpm exec wrangler ai-search jobs create {name}` で手動起動できる(§6 PIT-AISEARCH-008。初回体験を止めない)。検証 = アップロード直後に同期ジョブが増える + `GET /api/sync/status` が running → 完了に遷移
- **Phase 6 — 画面シェルと導線(FEAT-03 / FEAT-04)**: **UI はゼロから描かない**。まず `recipe.json` の `templates.ui[]` に従い、Win 総合検証済み UI 6 ファイル(`index.html` / `docs.html` / `chat.html` / `common.js` / `pdf-ingest.js` / `styles.css`)を `public/` へコピーし、`{{PRODUCT_NAME}}` を §9 の値で置換 → Phase 3 の API に配線する(パスと JSON 契約は `tests/fixtures/mock-api.mjs` が写している)。買い手の knob(§4 軽量設定: 配色・名前)は**コピー後に**当てる。その上で下の「画面仕様」と差分があれば画面仕様を正として直す。検証 = `node recipe-tests/ui/*.mjs --ui-dir public`(TEST-013〜018 / 025)+ design-review 忠実度モード(`assets/screens/` の `checks` を照合)+ PC / 狭幅の両方で横スクロールが出ない
- **Phase 7 — 総合検証**: search-verify スキルの手順(投入 → 同期 → スコープ検索 → ページ根拠 → 削除反映)。**スコープ検証は必ず逆方向テストまで**(別ナレッジの内容を質問して「記載がありません」になること。混入はこれでしか検出できない)。削除は KV / R2 の不在だけで完了にせず、PIT-AISEARCH-007 の追い同期と検索確認まで行う

### 画面仕様(FEAT-03 の正。Win 検証ビルド 2026-09-01 で確定)

- **共通シェル**: 素の HTML/CSS/JS で 3 ページを分ける(SPA にしない)。各ページの `.layout` 直下は共通サイドバー `<aside id="app-sidebar">` + `<main>` の 2 カラム。サイドバー本体は各 HTML に複製せず共通 JS の `mountSidebar()` で描画(項目は「ナレッジ一覧」「全体チャット」の 2 つ)。PC は左固定、狭幅(< 860px)は同じナビを上部 2 列へ変形。横方向のページはみ出しを出さない
- **1. ナレッジ一覧(`/`)**: 名前入力 + 作成ボタンの行、その下に説明欄(任意・1 行・200 字)とヒント文(FEAT-04)、カード一覧。カード = 名前・説明(あれば 2 行で省略)・作成日・主操作「開く」(下部横幅いっぱい・最小高さ約 46px)・危険操作「削除」。「開く」→ 資料一覧 `?kb={kb}`。**トップカードから個別チャットへ直接飛ぶ導線は置かない**(先に登録資料を確認できる導線が正)
- **2. 資料一覧(`/docs?kb=`)**: 見出し(ナレッジ名)の下に説明行(バッジ「説明」+ 本文 + ゴーストの「説明を編集」。押すとフォルダ名変更と同じインライン編集フォームが開き、保存で `PATCH /api/kb/:kb` に `description` だけを送る。空なら薄字の案内文。FEAT-04)、その直下に**アクセント色の「このナレッジにチャットで質問する」CTA**(→ 個別チャット)。以下、同期状態 / D&D アップロード / 反映遅延の説明 / 資料テーブル / 削除、の順。一覧の正は KV 台帳、画面は楽観更新、索引反映の時差は常に文言で示す
- **3. チャット(`/chat` と `/chat?kb=`)**: `kb` 無指定 = 全ナレッジ横断、指定 = 対象のみ。同じ画面でタイトル・スコープバッジ・戻りリンクだけ切り替える。右寄せ質問バブル / 左寄せ回答カード。回答の下に根拠ページ画像を最大 3 枚 + `{件数} sources` の折りたたみ(資料名・ページ・一致度・抜粋)。根拠画像はネイティブ `<dialog>` の中央モーダルで原寸比拡大(**全称セレクタの余白リセットが `<dialog>` の既定中央配置を消すため `margin: auto` を明示**。`width: min(920px, 94vw)` / `max-height: 94vh`)。回答追加時に強制スクロールしない(入力へのフォーカス戻しは `preventScroll` 付き)
- **デザイントークン(kote2 標準テーマの適用値)**: Noto Sans JP(見出し 800〜900 / 本文 400〜500)。クリーム背景 `#f0efe2` / オリーブ `#71804b` / 濃緑文字 `#2f3a1c` / 補助 `#5a6242` / アクセント `#b05c2e` / 白カード / 薄緑 `#dde0c8`。PC サイドバー幅 228px(オリーブ背景・現在地はクリーム反転)、メイン余白 上 32 / 左右 48 / 下 64px、ページ見出し 31px(狭幅 25px・左右余白 16px)。セクション見出しは左 5px オリーブ線。角丸 8〜10px + 細枠線で統一し**影は使わない**。CTA は通常 = オリーブ / 個別チャット主導線だけアクセント / 削除 = アクセントのアウトライン。根拠画像は PC 3 列(比率 3:2・中央約 5% 拡大トリム)、モバイルは横スクロール + scroll snap

## 6. 固有の地雷 + 直し方

1. **[PIT-WRANGLER-003] 同期用トークンを `.env` に書いた途端 `wrangler dev --remote` が認証エラーで落ちる**
   - 症状: 「Failed to establish remote session due to an authentication issue」
   - 原因: `CF_API_TOKEN` / `CF_ACCOUNT_ID` は wrangler の予約環境変数名。wrangler v4 は `.env` を自動読込し OAuth ログインよりこれを優先するが、同期専用権限しか無いので remote dev が拒否される
   - 直し方: アプリ用の環境変数名を `SYNC_API_TOKEN` / `SYNC_ACCOUNT_ID` のように予約名を避けて命名(コード・env・ドキュメント一括)。wrangler は OAuth に戻り、Worker へは `.dev.vars` 経由で届く
   - 確認環境: mac wrangler 4.127(2026-08)/ 回帰: TEST-002
2. **[PIT-AISEARCH-001] 即時同期 REST が 400(code 7003: Could not route)/ 404**
   - 症状: トークン・アカウント ID は正しいのに route 不能(7003)、または旧パスが 404
   - 原因: REST パスは 2 段階で変わった。(1) ハイフンの `ai-search` が正(アンダースコアの `ai_search` はバインディング名だけ)。(2) 2026-08-31 以降、**名前空間入りの新形式** `POST /accounts/{id}/ai-search/namespaces/{ns}/instances/{name}/jobs` が正で、旧 `PATCH /accounts/{id}/ai-search/instances/{name}/sync` は 404 を返す
   - 直し方: sync モジュールのパスを新形式(namespaces 入り)へ統一する
   - 確認環境: mac(2026-08)+ win(2026-08-31 新形式で実動作確認)/ 回帰: TEST-003
3. **[PIT-AISEARCH-002] チャットが 500(retrieval_type 'hybrid' is not available: keyword indexing is disabled)**
   - 症状: hybrid 検索を要求すると 500
   - 原因: ダッシュボード既定値で作ったインスタンスはキーワード索引がオフ
   - 直し方: `wrangler ai-search update {instance} --hybrid-search true` → 同期ジョブを 1 回蹴って再索引(数分)
   - 確認環境: mac(2026-08)/ 回帰: 手動(チャットが 500 にならない)
4. **[PIT-AISEARCH-003] スコープ検索が 0 件になる / 別ナレッジの資料が混入する(質問次第で「動いて見える」)**
   - 症状: kbId 指定チャットが 0 件、または他ナレッジのチャンクが sources に混ざる
   - 原因: フィルタが旧 AutoRAG 形 `{type:"eq", key:"folder", value:...}` だと現エンジン(schema_version 2)で未定義動作。正は MongoDB 風 `{folder: "{kb}/"}`(公式: ai-search → retrieval → filtering)
   - 直し方: 新形に変更し、**逆方向テスト**(他ナレッジの内容を質問して 0 件)まで検証する
   - 確認環境: mac(2026-08)/ 回帰: TEST-005 + 手動(逆方向)
5. **[PIT-PDFJS-001] 日本語 PDF が全ページ「文字なし」判定になり画像扱いされる**
   - 症状: テキスト埋め込みのある PDF なのに getTextContent が全ページ 0 文字 → 本文検索が効かない。検証側で Node の pdfjs-dist を素で回しても同じ 0 文字になり「テキスト層が無い」と誤診する
   - 原因: CID フォント(印刷入稿系日本語 PDF)の復号には CMap が必要で、pdf.js は既定で読み込まない
   - 直し方: `getDocument({ data, cMapUrl: <pdfjs-dist の cmaps/ URL>, cMapPacked: true })`。修正後は登録済み PDF を削除 → ブラウザ再読込 → 再アップロード → 同期(振り分けはアップロード時に確定)。教訓: 「0 文字 = テキスト層なし」と断定する前に CMap 指定で再検査
   - 確認環境: mac Chrome + Node(2026-08)/ 回帰: 手動(日本語 PDF 投入でテキストページが生まれる)
6. **[PIT-KV-001] 作成・削除がリロードしないと一覧に反映されない**
   - 症状: ナレッジ作成直後の再取得に新規分が出ない(数秒〜数十秒遅れ)
   - 原因: Workers KV は結果整合。書いた直後の読み直しに反映が間に合わないことがある
   - 直し方: 作成・削除・アップロードはサーバー応答を正として画面を直接更新(楽観更新)。一覧の再取得に依存しない
   - 確認環境: mac `wrangler dev --remote`(2026-08)/ 回帰: 手動(作成 → リロード無しで一覧に出る)
7. **[PIT-SLUG-001] 非 ASCII 名のナレッジ ID が衝突する**
   - 症状: 「テストナレッジ(2回目)」の ID が「2」になる(別の「〜(2)」系の名前と衝突)
   - 原因: slugify が ASCII 以外を落とした残りをそのまま採用していた
   - 直し方: 非 ASCII を含む名前は常にハッシュ ID(`k-{hash}`)へ。ASCII だけの名前のみスラッグ化
   - 確認環境: mac(2026-08)/ 回帰: 手動(日本語 + 数字名で作成し `k-` 始まりになる)
8. **[PIT-CHROME-001] ヘッドレス Chrome のモバイル幅スクショが「壊れて見える」(存在しないバグを追う)**
   - 症状: `--window-size=390,844` のスクショだけ右端が切れて見える(実ブラウザでは正常)
   - 原因: Chrome ヘッドレスは最小ウィンドウ幅 500px を強制(`--headless=new` でも同じ)。500px で描画 → 390px に切り取られる
   - 直し方: 疑ったらまず `document.documentElement.clientWidth` を実測(500 なら罠)。狭幅検証はローカル HTML に `<iframe width=390>` でアプリを読み込み、親を 500px 以上で撮る
   - 確認環境: mac Chrome(2026-08)/ 回帰: 手動(design-review 時)
9. **[PIT-AISEARCH-006] 旧 `AI` バインディング(`env.AI.autorag()`)経由だと新形フィルタが「Invalid input」で拒否される**
   - 症状: mac 検証で通っていた新形フラットフィルタ(`{folder:"{kb}/"}`)が、旧 AI バインディング経由の呼び出しでは Invalid input になりスコープ検索が組めない
   - 原因: フィルタを正しく受けるのは**専用 `ai_search` バインディング + `chatCompletions()`** の経路(pro 版 PIT-AISEARCH-005「`search()` 直呼びは filters を黙って無視」と同根。経路によってフィルタの受理形が異なる)
   - 直し方: バインディングを `ai_search` に統一し、検索・フィルタは `chatCompletions()` の `ai_search_options.retrieval.filters` 経由だけにする。`chatCompletions()` の戻り(`choices` / `chunks`)は画面の回答・sources 契約へ正規化する。開発時は `wrangler.jsonc` のバインディングに `remote: true` を付け、dev でも本物の AI Search / R2 / KV を参照する。移行後は**逆方向テストまで再検証**する(経路が変わるとフィルタ挙動の検証はやり直し)
   - 確認環境: win(2026-09-01 移行完了)/ 回帰: TEST-012 + 手動(逆方向)
10. **[PIT-AISEARCH-004] 日本語 CSV が索引内で文字化けし、検索に一切当たらない(エラーは出ない)**
   - 症状: CSV の内容を質問しても「記載がありません」。sources の excerpt が `è³ªå` のような化けた表(`## Sheet1 | ... |`)になる。R2 上のファイルは正常な UTF-8
   - 原因: AI Search の表形式変換(CSV→markdown 表)が BOM 無し UTF-8 を Latin-1 と誤読する。化けたまま索引されるので日本語クエリにヒットしない
   - 直し方: アップロード API で CSV に UTF-8 BOM(`EF BB BF`)を付与して R2 へ保存。`content-type: text/csv; charset=utf-8` 指定は効かない(両変種の同時投入で実走比較済み)。既存 CSV は削除 → 再アップロード → 同期
   - 確認環境: mac `wrangler dev --remote`(2026-08)/ 回帰: 手動(CSV 固有の内容を質問し excerpt に生の日本語が出る)
11. **[PIT-AISEARCH-007] 資料を削除して同期ジョブが終わっても、最初の確認では検索索引に残る**
   - 症状: KV 台帳と R2 オブジェクトは消えているのに、削除資料だけに含めた固有キーワードで質問すると同じ sources が返る。同期ジョブ 1 回の完了だけを見ると削除済みと誤判定する
   - 原因: R2 の削除と AI Search の外部索引更新は別処理で、Win 実走では最初の同期・待機後にも削除チャンクが残り、追い同期と追加待機で消えた。ジョブ作成成功や 429(直前ジョブに相乗り)は「検索結果から消えた」証明ではない
   - 直し方: 削除前にその資料だけの検証キーワードを控える → 削除後に同期を 1 回作成 → status 完了まで待つ → 同じ質問で sources を確認。まだ出る場合はレート制限間隔を守って追い同期を作成し、完了待ちと検索確認をもう一度行う。回数を決めず連打せず、最終条件は**削除資料の sources 0 件**にする。画面には索引反映の時差を常時表示する
   - 確認環境: win `wrangler dev --remote`(2026-09-01、追い同期 + 待機後に索引不在を確認)/ 回帰: TEST-020
12. **[PIT-WIN-DEV-001] Windows の `wrangler dev` が AI Search エラーの直後にプロセスごと終了する**
   - 症状: チャット API が 500 を返した後、ほかの正常な API まで接続不能になる。ターミナルは exit 1 で、`RangeError: Responses may only be constructed with status codes in the range 200 to 599` を残す
   - 原因: Windows 検証時の `wrangler dev` が使った Miniflare alpha では、リモート AI バインディングのエラー応答を処理する際に不正な status の `Response` を組み立て、Worker 1 リクエストの失敗ではなく開発サーバー全体を終了させる場合があった。アプリの全 API が同時に壊れたわけではない
   - 直し方: まず元の AI Search エラー(バインディング・filters・同期中など)をログから直す。その後 `pnpm dev` を再起動し、ログの `Ready on` に出た URL を正として `/api/kb` の 200 を確認してからチャットを再試験する。500 後もサーバーが生きている前提で検証を続けない
   - 確認環境: win Node 24 / wrangler 4.127.1 / miniflare 5.20260828.0-alpha(2026-09-01)/ 回帰: TEST-021

13. **[PIT-TS-001] `@cloudflare/workers-types` の `FormData.get()` が `string | null` 型で、`instanceof Blob` が型エラー(TS2358)になる**
   - 症状: アップロード API で `form.get("file") instanceof Blob` が「instanceof の左辺は any かオブジェクト型」で弾かれ、`typeof !== "string"` で絞ると `never` になって `.size` / `.arrayBuffer()` が使えない
   - 原因: workers-types 4.20260702 の FormData 宣言が File を含まない(実行時には File が来る)
   - 直し方: `form.get(...) as unknown as File | string | null` にキャストしてから `typeof === "string"` で絞る(実行時の挙動は不変)
   - 確認環境: win TS 5.9.3 / workers-types 4.20260702 / wrangler 4.129(2026-09-06 パッケージ再生)/ 回帰: TEST-001
14. **[PIT-TS-002] TS 5.9 の型付き配列ジェネリクスで `Uint8Array<ArrayBufferLike>` が R2 `put()` / `Response` 本文に渡せない(TS2322)**
   - 症状: `Uint8Array.from(atob(...), ...)` の戻りや `Uint8Array` 引数の関数戻りが `Uint8Array<ArrayBuffer>` に代入不可(SharedArrayBuffer を含む型が拒否される)
   - 原因: TypeScript 5.7 以降で `Uint8Array` が `ArrayBufferLike` ジェネリクスになった
   - 直し方: `new Uint8Array(await file.arrayBuffer())` を `Uint8Array<ArrayBuffer>` と明示し、サムネイルの base64 復号は `new ArrayBuffer(n)` に書き込んで `ArrayBuffer` を返す
   - 確認環境: 同上 / 回帰: TEST-001
15. **[NOTE] `wrangler.jsonc` の AI Search バインディングの書き方(2026-09-06 Win で `wrangler deploy --dry-run` が「AI Search Instance」として認識)**: `"ai_search": [{ "binding": "SEARCH", "instance_name": "{name}", "remote": true }]`。R2 / KV も `"remote": true` を付ける。`instance_name` は `vars.INSTANCE_NAME`(sync REST のパス)と同じ値にする

16. **[PIT-WIN-CURL-001] Windows の curl に日本語を引数で渡すと Worker 側で文字化けし「英語の質問だけ当たる」ように見える**
   - 症状: Git Bash から `curl -d '{"query":"日本語"}'` で `/api/chat` を叩くと、スコープ有無に関わらず 0 件や無関係なページが返る。英語の質問だけ正しく当たるため、フィルタや索引の不具合と誤診しやすい
   - 原因: Windows ネイティブの curl.exe に渡る引数が ANSI コードページ(932)経由で Shift-JIS 化され、Worker 側では壊れた文字列になる(Worker で質問文を `console.log` すると確認できる)
   - 直し方: 日本語を含む API 試験は curl を使わず、Node スクリプトで `fetch` + 質問一覧を JSON ファイルから読む。切り分けの最初に「Worker 側で受け取った質問文が正しいか」を見る
   - 確認環境: win Git Bash + curl.exe(2026-09-06 買い手側の実機検証)/ 回帰: 手動(search-verify 手順 3 の前提)
17. **[PIT-AISEARCH-008] 同期トークン未設定だと索引は定期同期(既定 6 時間)まで進まない。wrangler から手動でジョブを起動できる**
   - 症状: 資料を登録しても `GET /api/sync/status` が `configured: false` のまま検索に出ない。インスタンスの `stats` の Processing が数分以上減らないこともある(2 のまま 8 分。その間も検索には出ていた)
   - 原因: 即時同期は `SYNC_API_TOKEN` 経由の REST だけ。未設定なら次の定期同期(`sync_interval`)待ち。`stats` の集計は索引の実態より遅れる
   - 直し方: `pnpm exec wrangler ai-search jobs create {name}`(OAuth ログインで可・トークン不要)→ `jobs get {name} {job-id}` の `ended_at` で終了確認 → 実際の質問で当たるか確認。`stats` の Processing を完了条件にしない。README 手順の同期トークン設定が後回しでも初回体験は止まらない
   - 確認環境: win wrangler 4.129(2026-09-06 買い手側の実機検証)/ 回帰: 手動(TEST-006 は REST 設定後)
18. **[PIT-AISEARCH-009] 陽性対照は「sources 0 件」ではなく「他ナレッジのチャンクが無い」で判定する**
   - 症状: 単一ナレッジをスコープに、そのナレッジに無い内容を聞くと、回答は「記載がありません」なのに sources に自ナレッジのチャンクが 2 件ほど低スコア(0.42〜0.47)で並ぶ。「0 件にならない = フィルタ漏れ」と誤診する
   - 原因: reranking 有効時、スコープ内のチャンクがしきい値(0.4)をわずかに超えて返る。フィルタ漏れではない
   - 直し方: 陽性対照の合格条件は「sources の kbId がすべてスコープ内」+「回答が記載なし」。他ナレッジの kbId が 1 つでも混ざったらフィルタ不良として PIT-AISEARCH-006 / 003(pro は 005)を疑う。TEST-008 の「混入なし」もこの意味で判定する
   - 確認環境: win `wrangler dev --remote`(2026-09-06 買い手側の実機検証)/ 回帰: TEST-008 + 手動(陽性対照)

19. **[PIT-SETUP-KV-001] 既存の KV namespace を再利用する時、title が想定と違うとセットアップの自動検出が id を拾えない**
   - 症状: セットアップスクリプトが「KV の id を取得できませんでした」で終わり、`kv namespace create` も「既にある名前」で失敗する。`wrangler.jsonc` の id がプレースホルダのまま
   - 原因: 自動検出は title `{worker名}-REGISTRY` を探すが、以前に別名(例: `REGISTRY_PRO`)で作られていると一致しない。作成側も既存の `REGISTRY` と衝突する
   - 直し方: `pnpm exec wrangler kv namespace list` で目的の title の id を確認し、`wrangler.jsonc` に手で貼る。どの KV がこのビルド用かは中身の鍵(`folder:` があれば pro 版)で見分ける。Phase 1 の検証(プレースホルダが残っていない)を飛ばさない
   - 追記(2026-09-07 Win 再生で再発): wrangler 4 は `kv namespace create <名前>` の <名前> を**そのまま title にする**(旧版のような Worker 名の接頭辞は付かない)。照会が `{project}-REGISTRY` で作成が `REGISTRY` だと「照会では無し → 作成で旧 KV と衝突 → R2 だけ作られた状態で停止」になる。AI が §5 の文章から再導出すると同じ食い違いを起こすので、スクリプトは `templates/core` の参照実装をコピーする(再導出しない)。途中まで出来た状態からの再実行は `--reuse`
   - 確認環境: win wrangler 4.129(2026-09-06 / 09-07 買い手側の実機検証)/ 回帰: TEST-022(作成 KV の title を検査)
20. **[PIT-MULTIBUILD-001] 生成時期の違うビルド(例: 2026-08 の mac 実ビルドと 2026-09 の win 再生)が同じ KV・R2・インスタンスを共有すると、台帳・サムネイル・R2 キーの形式がずれる**
   - 症状: 資料一覧が「読み込みに失敗しました(reading 'toUpperCase')」で落ちる / サムネイルが 500 か壊れ画像 / md・csv が根拠(sources)に出ない / 画面から削除しても R2 と索引に実体が残る。検索と回答自体は両方で動くので気づきにくい
   - 原因: このレシピが契約として固定しているのは PDF の pageKey(§3-2)だけで、台帳の項目名(`id` / `size` / `keys` と `docId` / `kind` / `bytes`)、サムネイルの保存形式(JPEG バイナリと base64 文字列)、PDF 以外の R2 キー(`{kb}/名前` と `{kb}/{docId}__名前`)は再生ごとに実装が選べてしまう
   - 直し方: **分ける**(2026-09-06 kote2 決定。互換層は作らない — 別物であるべき 2 つが同名で相乗りしたのが原因で、見えてしまうこと自体が事故)。先にデータを消さず、後から建てた側の `wrangler.jsonc` の **4 か所(`name` / `vars.INSTANCE_NAME` / `bucket_name` / `instance_name`)を同じ接尾辞(例 `-win`)で揃えて**別名にし(`name` だけ変えても他は追従しない)、KV id をプレースホルダに戻してセットアップを再実行する。元の側のデータは触らない。**構造の直し**: セットアップスクリプトは 3 種を事前照会して同名が 1 つでもあれば何も作らず・書き換えずに止まり(`--reuse` を明示した時だけ引き継ぐ)、一覧・作成の失敗は非ゼロ終了、KV は作成・検索とも title `{project}-REGISTRY` で揃える(PIT-SETUP-KV-001 の再発も防ぐ)。台帳項目名・サムネイル形式・非 PDF キーの契約化は「同じプロジェクトを世代更新する時」の別課題として保留
   - 確認環境: mac 実ビルド(2026-08)+ win 再生(2026-09-06)の共有で買い手側が実測 / 回帰: TEST-022 + TEST-023
21. **[PIT-WIN-DEV-002] Windows で `wrangler dev` を止めても子プロセス(workerd)が残り、ポートを掴み続ける**
   - 症状: 起動元のシェルを止めても `http://127.0.0.1:8787` が応答し続け、次の `pnpm dev` が別ポートにずれる(古いコードが応答し続けて「直したのに直らない」に見える)
   - 原因: Windows では親プロセス終了時に workerd が道連れにならない
   - 直し方: `netstat -ano | findstr :8787` で PID を特定し、`Get-CimInstance Win32_Process` のコマンドラインが**このプロジェクトのパス**のものだけ `Stop-Process`。別プロジェクトの dev が同居していることがあるので workerd を無差別に kill しない。`wrangler r2 object get --pipe` を `head` にパイプすると固まるので `--file` で保存して読む
   - 確認環境: win wrangler 4.129(2026-09-06 買い手側の実機検証)/ 回帰: 手動(`Ready on` の URL とポートを毎回確認)
22. **[PIT-AISEARCH-010] 100 ページ級の PDF を登録すると 1 回の通信が 3〜5 分かかり、画面が「アップロード中…」のまま通信切れに見えて同じ資料を二重登録してしまう**
   - 症状: 90〜130 ページの PDF で登録の応答が返らない(データは登録済み。F5 で一覧に出る)。待てずに再登録すると同じ PDF が 2 件になり、片方を消しても索引にはしばらく残る(PIT-AISEARCH-007)。台帳の `docCount` も通信切れ分だけずれる
   - 原因: ページ分解(pdf.js)+ ページごとの R2 / KV 書き込みを 1 リクエストで待っているため、ページ数に比例して応答が遅れる。UI は応答が無いと状態を切り替えない
   - 直し方: 応答が無い時は台帳(`GET /api/kb/{id}/docs`)を確認して「登録しました」へ切り替える(最小改修)。文言に「100 ページ級は数分かかります。二重に登録しないでください」を出す。根本策はページ単位の分割送信(次の版の候補)
   - 確認環境: win Node 24 / wrangler 4.129(2026-09-07 買い手側の実運用: 16p = 34 秒 / 91p = 約 3 分 / 129p = 5 分)/ 回帰: 手動(Phase 4 の検証で 100 ページ級を 1 本入れる)
23. **[NOTE] 画像(JPEG / PNG)は AI Search が英語の説明文として索引する**(2026-09-07 Win 実運用): レシート画像は店名・日付・一部の品目は拾えるが金額は落ちる。金額まで検索したいなら登録時に Workers AI で文字起こしを足す(FEAT 候補・既定 OFF)。§3-1 の「画像も投入できる」は「写っている物の説明で検索できる」の意味で、OCR ではない
24. **[NOTE] `wrangler ai-search search ... --filter "folder=..."` は他フォルダのチャンクが混ざる**(2026-09-07 Win 実運用): CLI 側の挙動で、アプリの `chatCompletions` + `filters: { folder }` は混入なし。陽性対照(PIT-AISEARCH-009)や混入判定を CLI で行わず、アプリ経由(`pnpm ask --kb`)で見る

25. **[PIT-AISEARCH-011] 管理画面のプレイグラウンドで「No matching documents」なのに、アプリ経由の同じ質問はヒットする**
   - 症状: プレイグラウンドで日本語の質問が 0 件(英語の一般論だけ返る)。同じ質問を `pnpm ask` で投げると該当ページを根拠に回答する。「索引に入っていない」と誤診しやすい
   - 原因: インスタンス既定の検索設定(再ランク付け OFF・スコア閾値 0.4)で引くと、日本語質問のベクトルスコアが閾値の下に落ちる。アプリは `ai_search_options` で再ランク ON・件数を毎回上書きしているので当たる。`wrangler ai-search search --filter ...` でも `--reranking` 無しは 0 件、有りは 0.50 / 0.48 でヒットした
   - 直し方: プレイグラウンドで見せる時は「設定 → 検索 → 再ランク付け」を ON にする(または閾値を下げる)。「プレイグラウンドで出ない = 索引に無い」と断定せず、索引の有無は「アイテム」タブ(ファイルごとのステータス・チャンク本文・`folder` メタデータが見える)か `wrangler ai-search search --reranking --score-threshold 0` で確認する
   - 確認環境: mac wrangler 4.131 `wrangler dev --remote`(2026-09-16 講座版の再生・91 ページ日本語 PDF)/ 回帰: 手動(search-verify 手順 2 の「索引に入ったか」はアイテムタブで見る)
26. **[PIT-AISEARCH-012] 「0 件」を 1 回見ただけで判定しない — 同期完了後 15 分ほどは結果が揺れ、初めての言い回しの質問は 1 回目だけ 0 件になることがある**
   - 症状: (a) `jobs get` の ended が付いた直後〜15 分は、同じ質問が 0 件 → 8 件 → 0 件と揺れる(直接検索 `wrangler ai-search search --reranking` でも 4 回中 1 回が 0 件)(b) 同期から数時間経っていても、初めて投げる質問文が 0 件で、直後に同じ文で再質問すると 8 件当たる。同じ文を 6 回連続で投げると 6 回とも当たる
   - 原因: (a) ジョブの終了 = 索引の反映完了ではない(登録も削除も同じ。PIT-AISEARCH-007 と同根)(b) 未特定。類似キャッシュ(PIT-AISEARCH-013。0 件の応答は保存されないことを実測)や `query_rewrite` では説明しきれず、AI Search 側の初回経路の揺れとみている
   - 直し方: 0 件を見たら**同じ質問文でもう 1 回**投げてから判定する。検証手順(search-verify 手順 3〜5・TEST-007 / 008 / 106〜108)は「2 回投げて 2 回とも 0 件」を FAIL の条件にし、同期完了後は 1〜3 分置いてから始める。受講生向けの文言は「1 回目は出ないことがある。もう一度送る」
   - 確認環境: mac wrangler 4.131 `wrangler dev --remote`(2026-09-16〜17 講座版の再生)/ 回帰: TEST-024
27. **[PIT-AISEARCH-013] 類似キャッシュ(インスタンス設定 CACHE。既定 ON・強い・48 時間)はアプリ経由にも効く — 資料を直しても 48 時間は前の答えが返る**
   - 症状: 同じ質問文を 3 回投げると回答文が 1 文字違わず同一で所要 1.7 秒(LLM は普通ゆらぐ)。資料を再登録・再インデックスしても、似た言い回しの質問には古い回答が返る
   - 原因: インスタンス設定「CACHE → 類似性キャッシュ」。アプリは `ai_search_options.cache` を指定していないので、そのまま効く(プレイグラウンドも同じ)。鍵には絞り込み(filters)も含まれ、別ナレッジに絞った同じ質問文は使い回されず「記載なし」になった。0 件の応答は保存されず、次回は探し直す(PIT-AISEARCH-012 の (b) はキャッシュでは説明できない)
   - 直し方: 資料の再登録・再インデックスの効果を見せる時は、質問文を変えるか、設定のスイッチを OFF → ON してキャッシュを消す。特定の質問だけ避けたい時は `ai_search_options.cache` を 1 質問ごとに上書きする(既定 OFF の拡張候補。今の実装には無い)。削除反映(TEST-020)の判定は削除資料だけの固有キーワードで行うので影響を受けない
   - 確認環境: mac wrangler 4.131 `wrangler dev --remote`(2026-09-17 講座版の再生。Cloudflare Docs「Similarity cache」で per-request 上書きを確認)/ 回帰: 手動(同一質問 3 回の回答が同一・別スコープは非流用)
28. **[PIT-WRANGLER-004] 同じレシピの別生成物(双子)の `wrangler dev` が 8787 を掴んでいると、同梱スクリプト(`pnpm ask` / `pnpm ingest`)が双子へ向く**
   - 症状: `pnpm dev` の Ready on が 8788 なのに、`pnpm ask` の結果に見覚えのないナレッジ(別生成物の台帳)が出る。投入したはずの資料が「無い」。投入(`pnpm ingest`)を打つと双子の保管庫を汚す
   - 原因: `scripts/ask.mjs` / `scripts/ingest.mjs` の既定 URL が 8787 固定。双子が先に 8787 を取っていると、こちらは 8788 に逃げるがスクリプトは 8787 を叩く(PIT-WIN-DEV-002 の「ポートがずれる」と同じ入口。mac でも起きる)
   - 直し方: 必ず起動ログの Ready on を見て `--base-url http://127.0.0.1:8788`(または `BASE_URL` 環境変数)を付ける。または双子のサーバーを止めてから起動する。切り分けは `lsof -iTCP:8787 -sTCP:LISTEN` → その PID の cwd(`lsof -p PID | grep cwd`)で「どのフォルダのサーバーか」を見る。投入前は `GET /api/kb` の一覧が自分の台帳かを 1 回確認する
   - 確認環境: mac(2026-09-16 講座版の再生。`output/` に同レシピの双子が同居)/ 回帰: 手動(search-verify 手順の前提に追加)

## 7. 固有スキル / 道具

- `search-verify` — 投入 → 索引 → 検索 → 根拠 → 削除反映のどこが壊れているかを順に切り分ける検査スキル(ハマりどころの一次記録もここ)
- `design-review` — スクリーンショット → デザイン基準照合 → 修正のループ(ヘッドレス撮影の罠対策込み)
- `scripts/ingest.mjs` — 架空家電サンプル(マニュアル + FAQ)の一括投入(初回体験用)
- `check-sync.sh`(生成プロジェクトの scripts 配下)— Claude Code / Codex 両対応のスキル同期チェック

## 8. ハーネス宣言

Web 用途の標準一式(CLAUDE.md / README(md+html)/ AGENTS.md / dashboard.html / .claude/rules(secrets・context-hygiene・design)/ .project-memory / スキル同期 / kote2 標準テーマ)を templates/ から焼く。固有の上書き: 開発コマンドは `pnpm dev`(= `wrangler dev --remote`。**リモート接続モードが既定**、AI Search はローカルエミュレーションが無いため)/ 「できること」にサンプル投入・検索動作確認を含める。Windows で建てる場合は自己修復 hooks を配置しない(手動 self-heal のみ。settings.json は permissions だけ)。

## 9. 適応指示(環境差・安全側・固有値)

| 買い手ごとに変わる値 | 置き場 | 備考 |
|---|---|---|
| 画面のプロダクト名 `{{PRODUCT_NAME}}` | `templates/ui/*.html`(title / ブランド / フッター)| 既定「AI Search ナレッジ」。コピー時に置換(`recipe.json` の `placeholders`)|
| 管理の合言葉 | `.env` の `ADMIN_TOKEN` → `cp .env .dev.vars` | 買い手が任意に決める |
| 即時同期トークン | `.env` の `SYNC_API_TOKEN` | アカウント API トークン(権限: **AI Search: Edit + Auto Rag: Edit** の 2 行だけ)。検索実行(Run)は不要 |
| アカウント ID | `.env` の `SYNC_ACCOUNT_ID` | ダッシュボードで確認 |
| AI Search の名前空間 | `.env` の `SYNC_NAMESPACE` | 新形式 REST パスの `{ns}`。既定 `default`(2026-09 の Win 再生では実同期まで未検証。404 ならダッシュボードで名前空間を確認) |
| R2 バケット名 / KV title / インスタンス名 | `wrangler.jsonc` | 既定 `{project}-docs` / `{project}-REGISTRY` / `{project}`(`name` から派生する規約。ただし `bucket_name` / `instance_name` / `vars.INSTANCE_NAME` は個別に書かれているので `name` を変えても追従しない)。**同一アカウントに別の生成物(別マシン・別の版)が居るなら `name` / `vars.INSTANCE_NAME` / `bucket_name` / `instance_name` の 4 か所を同じ接尾辞(`-win` 等)で揃えて分ける**(名前はアカウント内で一意。セットアップが整合を検査して崩れていれば止まる。§6 PIT-MULTIBUILD-001) |
| Cloudflare アカウント | `wrangler login` | 買い手自身の OAuth |
| 公開先(workers.dev) | `pnpm deploy` 時 | **明示の合図があるまで deploy しない**(チャット API が開放されている試作のため、公開前チェックを促す) |

- **1 生成物 = 1 組のリソース。保管庫(KV / R2 / インスタンス)を他の生成物と共有しない**: データはマシンではなく Cloudflare 側にあるので、同じ名前で建てた別の生成物(別マシン・別の版)からも見えてしまい、台帳・サムネイル・R2 キーの形式がずれる(§6 PIT-MULTIBUILD-001)。共有して互換させるのではなく、名前を分けて別物にする
- 安全側デフォルト: `.env` / `.dev.vars` は gitignore 済み・値の表示やログ出力をしない / 実在メーカーの資料を教材・配布物に使わない(同梱の架空サンプルで)/ Free プラン内なら課金は発生しない(超過は停止する)構造を README で説明
- コスト注意(README に含める): Workers AI 10,000 ニューロン/日・KV 書き込み 1,000/日(大型 PDF 数冊/日で到達)・R2 10GB はアカウント合算

## 10. 完成判定(買い手の AI が自己検証)

§1 機能構成表に対し:
- required = すべて PASS(1 つでも FAIL なら未完成)
- optional-enabled = enabled のものは PASS / disabled にしたものは SKIP
- optional-disabled = なし(このレシピは未使用)
かつ §5 各 Phase の検証が緑。

| TEST ID | 対象 | 種別 | tier | 検証方法 | 期待値 |
|---|---|---|---|---|---|
| TEST-001 | — | auto | smoke | `bash recipe-tests/smoke-typecheck.sh` | 型エラー 0(`pnpm typecheck` を包む) |
| TEST-002 | PIT-WRANGLER-003 | auto | smoke | `! grep -q "^CF_API_TOKEN=" .env.example` | `.env.example` に予約名の行が無い(`grep -L` は BSD / GNU で終了コードが違うので使わない) |
| TEST-003 | PIT-AISEARCH-001 | auto | smoke | `grep -q "ai-search/namespaces" src/sync.ts` | 名前空間入りの新形 REST パスを使用 |
| TEST-004 | CORE-01 | auto | full | `curl -fsS -o /dev/null "http://localhost:8787/api/kb"` | 台帳 API 200 |
| TEST-005 | PIT-AISEARCH-003 | auto | smoke | `grep -q "filters: { folder:" src/search.ts` | 新形フィルタを使用 |
| TEST-006 | CORE-04 | auto | full | `curl -fsS "http://localhost:8787/api/sync/status"` | `configured` を含む JSON |
| TEST-007 | CORE-02 | manual | full | テキスト PDF を投入 → 同期 → 内容を質問 | 該当ページのサムネイル + sources |
| TEST-008 | CORE-01 | manual | full | 別ナレッジの内容をスコープ付きで質問(逆方向) | 「記載がありません」+ 混入なし |
| TEST-009 | CORE-03 | manual | full | 資料を削除 → 同期完了後に同じ質問 | 削除資料が sources に出ない |
| TEST-010 | FEAT-01 | manual | full | スキャン(画像)PDF を投入 → 同期 → 見出しレベルを質問 | 画像索引由来の回答 or 正直な不在回答 |
| TEST-011 | CORE-05 | auto | smoke | `grep -q "MAX_FILE_BYTES" src/index.ts` | 4MB 入口ガードが実装されている(PDF 以外に適用。PDF 全体には掛けないこと — CORE-05) |
| TEST-012 | PIT-AISEARCH-006 | auto | smoke | `grep -q "chatCompletions" src/search.ts` | 検索が `ai_search` バインディングの chatCompletions 経由 |
| TEST-013 | FEAT-03 | auto | full | `node recipe-tests/ui/sidebar-on-all-pages.mjs --ui-dir public` | 3 ページ(`/` `/docs?kb=` `/chat`)すべてに `aside#app-sidebar`(ナレッジ一覧 / 全体チャット)+ 390px で横はみ出しなし |
| TEST-014 | FEAT-03 | auto | full | `node recipe-tests/ui/open-goes-to-docs.mjs --ui-dir public` | カードの「開く」(高さ約 46px・横幅いっぱい)→ `/docs?kb={kb}` へ遷移。カードに個別チャット直行リンクが無い |
| TEST-015 | FEAT-03 | auto | full | `node recipe-tests/ui/docs-has-accent-cta.mjs --ui-dir public` | 資料一覧の見出し直下に `--accent` 背景の「このナレッジにチャットで質問する」CTA(→ `/chat?kb=`) |
| TEST-016 | FEAT-03 | auto | full | `node recipe-tests/ui/modal-center.mjs --ui-dir public` | サムネイルクリックで `dialog[open]`(showModal)。中心がビューポート中心 ±40px・画面内に収まる |
| TEST-017 | FEAT-03 | auto | full | `node recipe-tests/ui/modal-backdrop-close.mjs --ui-dir public` | ダイアログ外(背景)クリックで閉じる |
| TEST-018 | FEAT-03 | auto | full | `node recipe-tests/ui/no-forced-scroll-on-answer.mjs --ui-dir public` | 入力欄が画面外にある状態で回答が追加されても `window.scrollY` が変わらない |
| TEST-019 | CORE-02 | auto | full | `bash recipe-tests/evidence-image-width-1980.sh` | 根拠表示用ページ画像の横幅が 1980±2px(PNG / JPEG ヘッダを読む・外部依存なし)。画像未指定なら `SKIP:` を出して exit 0(PASS 扱いにしない。取り方はスクリプト冒頭) |
| TEST-020 | PIT-AISEARCH-007 | manual | full | 削除資料だけの固有キーワードを控える → 資料削除 → 同期完了待ち → 同じ質問。残存時は間隔を空けて追い同期 → 再確認 | KV / R2 不在に加え、削除資料の sources 0 件(初回同期だけで判定しない) |
| TEST-021 | PIT-WIN-DEV-001 | manual | full | Windows でチャット 500 発生時にターミナルの exit / RangeError と `curl /api/kb` を確認。プロセス終了なら元エラー修正後に `pnpm dev` を再起動 | `Ready on` の URL で `/api/kb` が 200 に戻り、開発サーバー終了とアプリ全体故障を混同しない |
| TEST-022 | PIT-MULTIBUILD-001 | auto | smoke | `bash recipe-tests/setup-cloudflare-boundary.sh` | 疑似 wrangler で 28 ケース PASS: 新規 / R2 空 / 3 種のいずれかだけ既存・全部既存 → exit 1・設定不変・作成なし / `--reuse` は無いものだけ作成 / 一覧の取得失敗・JSON でない・想定外の形・同名 KV に id 無し → exit 1 / 作成失敗・KV id 読取失敗 → exit 1・設定不変 / 不明な引数 exit 2 / `name` だけ改名 → CLI を呼ばず exit 1 / 作成 KV の title が `{project}-REGISTRY` / **設定の形式**(複数行 JSON・id が binding より前・偽物コメント + 末尾カンマ・id キー無し)でも建ち、書いた id を読み戻せてコメントが残る / 形式の負例(binding `REGISTRY` 無し・壊れた JSONC)→ CLI を呼ばず exit 1・設定不変 |
| TEST-023 | PIT-MULTIBUILD-001 | manual | full | 同名のバケット / インスタンスが実在するアカウントで生成物のセットアップスクリプト(`setup-cloudflare.sh`。`--reuse` なし)を実行 | 「既にあります」を出して exit 1・何も作らず・`wrangler.jsonc` 不変(mac 2026-09-07 / win 2026-09-07 実測) |
| TEST-024 | PIT-AISEARCH-012 | manual | full | 同期完了後 1〜3 分置く → スコープ付きの質問を投げる → 0 件なら**同じ質問文をもう 1 回** | 2 回連続 0 件のときだけ FAIL(1 回目 0 件 → 2 回目ヒットは PASS。他の手動テストの「0 件」判定もすべてこの規則で行う) |
| TEST-025 | FEAT-04 | auto | full | `node recipe-tests/ui/kb-description-editable.mjs --ui-dir public` | 作成フォームの説明欄(任意)に入れて作成 → カードに説明が出る / 空でも作成でき空の枠を出さない / 資料一覧の「説明を編集」→ 保存 → 再読み込み後も残る / 説明だけの保存でフォルダ所属(pro 合成時)が消えない |

UI 動作テスト(TEST-013〜018 / 025)の約束: `recipe-tests/ui/*.mjs` は `--ui-dir public` を渡すと `recipe-tests/fixtures/mock-api.mjs`(架空データの偽 API)を自前で起動して生成物の `public/` を動かす = Cloudflare アカウント不要。ブラウザはダウンロードせず PC の Google Chrome(無ければ Microsoft Edge)を `channel` で使い、どちらも無ければ **exit 3 = SKIP**(PASS にしない)。`--base-url` で起動済みサーバーを指す使い方もできる(`/__mock/reset` を使うテストはモック限定)。参照スクショの再撮影は `node recipe-tests/ui/screens.mjs --ui-dir public --out assets/screens`。モック API の `PATCH /api/kb/:kb` は実 API と同じく**送られたキーだけ変える**(2026-09-21 までは `folderId` を省くと所属を消していた = 生成物側で「説明だけの保存でフォルダ所属が消える」偽陽性を出す。TEST-025 の 4 項目目が回帰)。

深い実装(ルーター全文・台帳・ページ分解 JS の実体)は §5 の順路 + `knowledge/cloudflare-workers.md` + AI の一般知識から建てる(シード型)。**UI 層(`templates/ui/`)と検索モジュール(`templates/core/search.ts`)だけは結晶化で昇格した参照実装が正本**で、コピーしてから配線する。再生の最中に `output/` を読まない(builder.md ⑥。読んでよいのはこのパッケージ内 + `knowledge/` + ビルダー `templates/`)。

<!-- ============================================================ -->
<!-- recipe-notion-wp — 設計書(シード)第一号 兼 「型」のお手本        -->
<!-- 由来: 三度の実ビルドを結晶化 — output/notion-style-wp(初号)+         -->
<!--       output/notion-note-wp(ライブ捕捉。3カラム化 + ピン留め + §6 地雷)+ -->
<!--       output/notion-notebook(③これ作って実走 2026-06-17。§6-3 の orderby=menu_order 400 を逆輸入)。 -->
<!--       建てる順路(§5)と地雷の直し方(§6)は当事者文脈から結晶化。       -->
<!-- バージョンは git で管理(ファイル名に付けない)。                   -->
<!-- 状態: builder.md 配線済み / 三度の実ビルドで結晶化済み / build-dist 登録済み(PRO_RECIPES。Pro ZIP 同梱)。 -->
<!-- ============================================================ -->

# recipe-notion-wp — Notion 風 WordPress

「WordPress を Notion のように使う」自作ブロックテーマを再現する設計書(シード)。

CONCEPT.md §7「設計書(シード)モデル」の第一号 兼 型のお手本。③(買い手が「これ作って」)で
ビルダーがこのファイルを読んで生成を駆動する。ビルダー知識の前提を最小にし、**単体でも読めるように**書く。

- 製品名: Notion 風 WordPress
- 用途分類: **Web**(builder.md の用途判定で Web。Q1.5 サーバー要件あり)
- 必要ビルダー VERSION: 3.9.0
- 検証ステータス: `verified` — skeleton(骨組みのみ)/ experimental(未実証)/ verified(実ビルド結晶化済み)。verified だけが配布対象
- 動作確認: `mac ✅` / `win ⬜` — 実機で建てて緑を取れた OS(⬜=未検証=動かない確証ではない)
- 配布元検証: `✅` — 配布元(kote2)が実機で最終サインオフ
- **この設計書の肝**: §5「再現の順路」= 完成形(What)だけでなく **建てる順番と各段の検証(How)** を持つ。
  「これ作って」が失敗する典型は説明不足ではなく「一気に作って動かない」。順路 + 検証でそれを潰す。

---

## 1. これは何 / 機能構成 + 完成形(受け入れ基準)

WordPress を「管理画面に行かず、Notion のように」使えるブロックテーマ。

### 機能構成(★ここだけが必須/任意/不採用を決める正本。他章はこの表を参照する)

| ID | 機能 | 状態 | Phase | 完成判定 |
|---|---|---|---|---|
| CORE-01 | リフレッシュなし SPA(差し替え遷移) | required | Phase 2 | PASS 必須 |
| CORE-02 | 右パネル 2 モード(閲覧 50% スライド / 編集 100% フェード iframe) | required | Phase 3 | PASS 必須 |
| CORE-03 | 並べ替えの書き戻し(`menu_order` 永続) | required | Phase 5 | PASS 必須 |
| LAYOUT-01 | 3カラム(左サイドバー/中央リスト/右パネル。形は軽量 knob で 2ペイン) | required | Phase 1 | PASS 必須 |
| FEAT-01 | front 編集(`canEdit` ゲート + iframe 編集) | optional-enabled | Phase 4 | enabled なら PASS 必須 |
| FEAT-02 | ピン留め(post meta `_pinned`) | optional-enabled | Phase 6 | enabled なら PASS 必須 |
| FEAT-03 | 固定ページのサイドバー直リスト | optional-enabled | Phase 6 | enabled なら PASS 必須 |
| FEAT-04 | インライン DB(単一 CPT + タクソノミー) | optional-disabled | Phase 7 | 既定 SKIP |
| FEAT-05 | Notion → WordPress 移行(冪等) | optional-enabled | Phase 8 | enabled なら PASS 必須 |
| EXCL-01 | AI 投稿連携(n8n MCP) | excluded | — | 別レシピ `recipe-ai-posting`(§9) |

> 状態語彙は `required / optional-enabled / optional-disabled / excluded` の 4 つだけ([templates/recipe/recipe-template.md](../templates/recipe/recipe-template.md))。`FEAT-01` front 編集を disabled にすると「閲覧専用の Notion 風ビューア」になる(魔法のタネ②を外す判断。§3-2)。

### 完成形(受け入れ基準)
- [ ] `required`(CORE-01〜03 / LAYOUT-01)がすべて緑
- [ ] `enabled` な `optional`(既定では FEAT-01/02/03/05)がすべて緑。`optional-disabled`(既定 FEAT-04)は **SKIP=欠落ではない**
- [ ] ローカル(wp-env)で上が動く ← **ここまでが「完成」。公開は別の合図があってから(§9)**

## 2. スタック

| 層 | 採用 | 備考 |
|---|---|---|
| 母体 | WordPress **自作ブロックテーマ**(PHP) | headless にしない(理由は §4) |
| ローカル開発 | **wp-env**(Docker) | `pnpm wp:start` で使い捨て WP |
| ビルド | **Vite** + manifest | `theme/build/` を functions.php が enqueue |
| CSS | **Tailwind v4**(`@theme`)+ `theme.json` | |
| フロント挙動 | **Alpine.js** + WordPress **REST API** | 素の JS でなく Alpine(状態/ストアが要るため) |
| 移行 | `@notionhq/client` + tsx | `notion-migration` スキルが使う |
| パッケージ | **pnpm** | `knowledge/pnpm.md` の予防策を適用 |

## 3. アーキの肝 = 魔法のタネ(★変えちゃダメ。Notion 風の本体)

ここを崩すと「ただの WordPress テーマ」に戻る。再現必須:

1. **リフレッシュなし SPA(差し替え遷移)**: 本文側だけを REST + Alpine で差し替え、ページ遷移・全体再読込をしない。これが「Notion 風」の正体。**レイアウト(3カラム既定 / 2ペイン簡易)は presentation なので §4 の knob**(魔法はペイン数でなく「遷移しないこと」)
2. **front 編集の安全パターン**: `wp_localize_script` で `restUrl / nonce / canEdit(current_user_can) / adminUrl` をフロントに渡し、**`canEdit` が true の時だけ**編集 UI(トップバー + iframe 編集フレーム)を出す。書き込みは必ず nonce 検証 + 権限チェック
3. **並べ替えの書き戻し**: `menu_order` を REST に公開(post は自前で `register_rest_field`、CPT は page-attributes でコアが出す)。同順は日付降順でフォロー
4. **移行は「1 件で型 → 本番一括」+ 冪等**: Notion ページ ID をメタに保存し、再実行で重複を作らない
5. **インライン DB は「単一 CPT + タクソノミー」**: 「1 コレクション = 1 CPT」で増やさない。単一 CPT(例 `course`)に分類タクソノミー(コース/セクション)を足す形にすると、**コレクション追加がコード変更ゼロ**になる

> ★この §3 は **スタック非依存の「魔法」**(リフレッシュなし SPA / canEdit ゲート編集 / 冪等移行)。別スタックで建てる時もここは保つ(§4 の別スタック注記)。

## 4. 改変の余地(★変えていい。③ でヒアリングして見せてから建てる。サイレント適用しない)

knob を **3 分類**で持つ。粒度を混ぜると「WP→Next は少し変えるだけ」と誤認する事故が起きるため(状態=必須/任意は §1 表が正本。ここは「どう変えられるか」だけ)。

### 軽量設定(設計を変えず差し替え。サイレント適用してよい唯一の層)
- **配色・フォント**: design トークン(`@theme` / `theme.json`)で差し替え
- **レイアウトの形**: 3カラム(既定)↔ 2ペイン(LAYOUT-01 の形違い)。記事が増える用途は3カラム必須(2ペインはサイドバーが破綻。notion-note-wp の実機指摘で確定)
- **ダーク/ライト既定**: 既定ダークは作者の好み(§9 で knob 化)
- **wp-env ポート**: 既定 8888。他の wp-env と同時起動するなら別ポート(§6-11)

### 機能モジュール(ON/OFF で Phase とテストが増減。状態は §1 表)
- **FEAT-01 front 編集**: 既定 ON / OFF にすると閲覧専用 Notion 風ビューア
- **FEAT-02 ピン留め**: 既定 ON。post meta `_pinned` + サイドバー上部固定(§5 Phase 6)
- **FEAT-03 固定ページのサイドバー直リスト**: 既定 ON
- **FEAT-04 インライン DB**: 単一 CPT + タクソノミー(§3-5)。既定 OFF
- **FEAT-05 Notion 移行**: 既定 ON

### 派生アーキ(★knob ではない。魔法のタネだけ移植して別実装=実質「別レシピ」)
- **母体**: 自作テーマ(既定)↔ headless(Astro/Next)。完成版は自作テーマ採用(front 編集の自作負担が headless より軽い)。headless 化は「少し変える」ではなく**再実装**(下の射程)

**③ 適応の射程(正直な線引き)**:

- **同一スタックでデザイン/コンテンツ違い**(例: Web メディアを横展開)= 上の knob を差し替えるだけの**高速・確実なケース**。量産で一番効く
- **別スタック**(例 PHP/WP → React/Next)= 『少し変える』ではなく**再実装**。§3 の魔法のタネだけ移植し、§2・§5・§6 は当該スタックで作り直す。AI が差分を判断して**提案 → ユーザー GO**

## 5. 再現の順路(Phase + 各段の検証)★最重要

**いきなり全部作らない。** 1 Phase 建てる → その場で検証(緑)→ 次へ。各 Phase 後に design-review を 1 周。
大きな構造変更の前にリビジョン保存。この順は実ビルドが通った道そのもの。

### Phase 0 — 土台(pnpm / wp-env / Vite)
作る: テーマ骨組み + ビルドパイプライン。
検証: `pnpm wp:start` で WP が立つ / `pnpm build` で `theme/build/` と `build/.vite/manifest.json` 生成 / テーマ有効化で functions.php が enqueue。

### Phase 1 — 3カラム静的(見た目の骨)[LAYOUT-01 / required]
作る: app-shell(左サイドバー | 中央リスト | 右パネル)。サイドバーは📌ピン留め / カテゴリ / 固定ページの3セクション。*2ペイン簡易版を選んだ場合はサイドバー + 右本文の2分割*。
検証: トップで3カラムが描画 / カテゴリ一覧が出る。design-review で「左 240–280px / 静かなトーン / 中央に視線」を確認。

### Phase 2 — リフレッシュなし遷移(魔法のタネ①)[CORE-01 / required]
作る: Alpine `workspace` コンポーネント。REST でカテゴリ→中央に記事一覧、記事クリックで右パネルに差し替え。ページ遷移しない。
検証: クリックで**全体再読込なし**に中央/右だけ変わる。**プレーンパーマリンクでも REST が通る**こと(§6-2)を `curl` で確認。

### Phase 3 — 右パネル 2 モード(閲覧ピーク / 編集フレーム)[CORE-02 / required]
作る: `$store.peek`(全ページ共通出力)。閲覧=右から横 50% スライド + 外側クリックで閉じる。編集・新規・管理=右 100% フェード iframe。**スライドとフェードを混ぜない**(挙動で閲覧/編集を区別)。
検証: 一覧から記事をピーク(50% スライド)→ 外側クリックで閉じる / 編集系は 100% フェードで開く。単一記事ページでもピークが出る。

### Phase 4 — front 編集(魔法のタネ②)[FEAT-01 / optional-enabled。disabled なら SKIP=閲覧専用]
作る: `wp_localize_script` ブリッジ(restPosts / restPages / restCategories / nonce / canEdit / adminUrl / newUrl / currentId)。`canEdit` ゲートでトップバー(新規 / 管理)+ ピークの編集 + iframe 編集フレーム。**localize の戻り値は文字列化される**ので `currentId` 等は JS 側で `Number()`(§6-1)。
検証: **非ログインで何も出ない** / 編集者でトップバーが出る / edit で右 100% にエディタが開く / トップで `posts/0` を取りにいかない(currentId の `"0"` truthy 回避、§6-1)。

### Phase 5 — 並べ替え(魔法のタネ③)[CORE-03 / required]
作る: `menu_order` を REST 公開(post=`register_rest_field`、CPT=page-attributes)+ **`orderby=menu_order` を collection params の enum に追加**(忘れると並べ替え取得が 400。§6-3 ②)。`reorderable` mixin + 中央リストの draggable 行。nonce 付き POST で書き戻し。
検証: `?orderby=menu_order&order=asc` が **200**(400 でない)→ ドラッグ → REST 200 → **リロードしても順序が残る**(DB に `menu_order` が入る)。元に戻せる。

### Phase 6 — ピン留め / 固定ページ(FEAT-02 + FEAT-03 / optional-enabled。disabled なら SKIP)
作る: post meta `_pinned` を `register_post_meta`(show_in_rest + `auth_callback` で `edit_post` ゲート)。サイドバー上部「📌 ピン留め」(`_pinned=true` を日付降順)。固定ページは localize の `restPages`(`wp/v2/pages`)をサイドバーに直リスト。`openPeek(id, type)` で post / page を出し分け(編集は `post.php?post=ID` が両型に効くので分岐不要)。
検証: `wp post meta update <id> _pinned 1` → REST `meta._pinned: true` → サイドバー上部に出る / canEdit 時だけピン切替ボタン / 固定ページがサイドバーに出てピークで開く。

### Phase 7 — インライン DB(単一 CPT + タクソノミー)[FEAT-04 / optional-disabled。既定 SKIP。ON にした時だけ作る]
作る: 単一 CPT(例 `course`)+ 分類タクソノミー。ショートコードでグルーピング表示。
検証: ショートコードでコレクションが表示 / **新コレクション追加にコード変更が要らない**(タクソノミーのターム追加だけ)。

### Phase 8 — Notion 移行(再利用される魔法)[FEAT-05 / optional-enabled。disabled なら SKIP]
作る: `notion-migration` スキル。1 件で型 → 人間が確認 → 本番一括。Notion ページ ID をメタに保存。
検証: **再実行で重複しない**(冪等)/ 未対応ブロックは握りつぶさずログ。

> 完成 = §1 機能構成表に対する 3 値判定が通る(§10)、かつ `scripts/validate-output.sh` が PASS。公開・デプロイは §9 の合図があってから。

## 6. 固有の地雷 + 直し方(★実ビルドで踏んだ地雷を結晶化。逆抽出では拾えないプロセス知)

実ビルドで実際に踏んだもの。**名前だけでなく直し方**を残す(ここが再現の時短になる)。
各地雷は固定 ID(`PIT-{ドメイン}-{3桁}`)+ 確認環境 + 回帰を持つ([templates/recipe/recipe-template.md](../templates/recipe/recipe-template.md) の PIT 規約)。

> **環境(wp-env / Docker / git / DNS)の地雷は [knowledge/wp-env.md](../knowledge/wp-env.md) に集約**(全 WordPress レシピ共通)。ここ §6 は notion-wp 固有のコード地雷だけ。

1. **[PIT-WP-JS-001] 文字列化された値の `"0"` が truthy(最凶バグ。data-* だけでなく `wp_localize_script` の戻り値も)**
   `data-section="0"` を `dataset.section` で読むと文字列 `"0"`(truthy)。「0 番セクションで絞り込み」が誤発火し**一覧が全部消える**。**同じ罠が `wp_localize_script` にもある**: PHP で `int 0`(例 `currentId`)を渡しても JS 側は文字列 `"0"` になり、`if (CFG.currentId)` が truthy → `posts/0` を取得して **404**。
   直し方: **ID/フラグなど数値が要る値は JS 側で必ず `Number()` してから判定**(`Number(this.$root.dataset.section) || 0` / `const cid = Number(CFG.currentId) || 0; if (cid) this.open(cid)`)。data-* も localize 戻り値も「文字列」と疑う。**症状は「項目がありません」/「posts/0 が 404」。REST は正常なのに front が空・誤取得なら真っ先にここ。** 思い込みでなくブラウザ DOM で検証。
   確認環境: mac wp-env 実ビルド(2026-06)/ 回帰: 手動(§5 Phase 4 検証=トップで posts/0 を取らない)

2. **[PIT-WP-REST-001] プレーンパーマリンクで `/wp-json/` が死ぬ**
   `rest_url()` が `http://host/index.php?rest_route=/` を返す環境では `/wp-json/...` が解決せず**トップページ HTML が返る**。
   直し方: フロントの `restUrl()` で `index.php?rest_route=` 形式を扱う。REST URL は `/?rest_route=/wp/v2/...` を使えば設定非依存で必ず通る。**テーマでも外部連携(n8n 等)でも刺さる共通地雷。**
   確認環境: mac wp-env 実ビルド(2026-06)/ 回帰: TEST-002(§10 マトリクス)

3. **[PIT-WP-REST-002] コア `post` の `menu_order` が REST に出ない + `orderby=menu_order` が enum 検証で 400(★後者は notion-notebook 実ビルドで発見 2026-06-17)**
   直し方(2段階。**両方要る**): ①`register_rest_field('post','menu_order', ...)` で get/update を自前提供(update は `current_user_can('edit_post')`)+ `rest_post_query` で `orderby=menu_order` 時に `menu_order ASC, date DESC`。CPT は page-attributes でコアが自動で出すので不要。②**それだけだと `?orderby=menu_order` が `rest_invalid_param`(HTTP 400「orderby is not one of ...」)で弾かれる** — REST は collection params の **enum** で `orderby` を検証し、`menu_order` は既定の許可値に無い。`rest_post_query`(クエリ改変)が走る**手前**で拒否されるので①の並べ替えロジックに到達しない。`rest_post_collection_params` フィルタで enum に追加する:
   ```php
   add_filter('rest_post_collection_params', function ($params) {
     if (isset($params['orderby']['enum']) && !in_array('menu_order', $params['orderby']['enum'], true)) {
       $params['orderby']['enum'][] = 'menu_order';
     }
     return $params;
   });
   ```
   症状は「並べ替え用に `?orderby=menu_order&order=asc` を投げると 400・本文は `code: rest_invalid_param`」。①だけ入れて②を忘れると気づきにくい(コードは正しいのに REST が 400)。**検証は実機 `curl '/?rest_route=/wp/v2/posts&orderby=menu_order&order=asc'` で 200 が返ること**。
   確認環境: mac wp-env(notion-notebook 2026-06-17)/ 回帰: TEST-003(§10 マトリクス)

4. **[PIT-WP-THEME-001] FOUC(ダーク/ライトの白チラつき)**
   直し方: `wp_head`(priority 0)で描画前に `localStorage` から `data-theme` を確定する inline スクリプト。既定はダーク。
   確認環境: mac wp-env(2026-06)/ 回帰: 手動(リロード時の白チラつきを目視)

5. **[PIT-PNPM-001] pnpm の ignored-builds → exit 1**
   直し方: `pnpm-workspace.yaml` の `allowBuilds: true` + `.npmrc` の `verify-deps-before-run=false`(`knowledge/pnpm.md` 準拠)。**wp-env 構成では esbuild/vite に加えて `fs-ext-extra-prebuilt`(wp-env がファイルロックに使う)も `allowBuilds` に要る**。許可リストに無いと初回 `pnpm install` が `ERR_PNPM_IGNORED_BUILDS: fs-ext-extra-prebuilt` で止まる(プレビルトバイナリなのでビルド自体は一瞬)。
   確認環境: mac/win 実ビルド(2026-06)/ 回帰: 手動(まっさら環境で `pnpm install` が exit 0)

6. **[PIT-WP-ENV-001] `.wp-env.json` の二重マウント**(`themes[]` と `mappings`)
   直し方: どちらも同じテーマを指すよう整合させる(片方だけだと反映されない/ズレる)。
   確認環境: mac wp-env(2026-06)/ 回帰: 手動(テーマ編集が反映されるか)

7. **[PIT-ALPINE-001] x-html で注入した HTML の中で Alpine が動かない**
   直し方: 動的注入(固定ページ本文のショートコード等)後に `Alpine.initTree(el)` を呼んで再初期化。
   確認環境: mac wp-env(2026-06)/ 回帰: 手動(動的注入部の Alpine ディレクティブが効くか)

8. **[PIT-PROC-001] リファクタで機能が静かに消える / 残骸が残る**
   実例: 講座を単一 CPT に作り替えた際、並べ替え機能が消失。Edit が prior-Read 無しで黙って失敗し、古いブロックが残った。
   直し方: 構造変更時は mixin(`...reorderable` 等)と draggable 属性を**意識して持ち越す**。変更後に**古いシンボルを grep**して残骸/重複を潰す。
   確認環境: mac 実ビルド(2026-06)/ 回帰: 手動(構造変更後に旧シンボルを grep)

9. **[PIT-WP-UI-001] row-handle が静止スクショに写らない(地雷ではなく仕様)**
   `.row-handle` は通常 opacity 0、行ホバーで 0.55(Notion 風・意図通り)。**バグと誤認して「直さない」。** ドラッグ可否は静止画でなく DOM/CDP で検証。
   確認環境: mac(2026-06)/ 回帰: 手動(DOM/CDP で draggable を確認。静止画で判定しない)

10. **[PIT-ALPINE-002] Alpine 式に生の `<` / `>` を書くと WordPress の texturize で Alpine が全停止(★最凶・このスタック固有)**
   block テンプレの HTML はレンダリング時に texturize され、属性値中の生 `>` の後ろに `&#8230;` 等が注入されて式が壊れる。`x-show="pinned.length > 0"` の `>` が壊れると Alpine が `Alpine.start()` で構文エラー → **Alpine 全体が停止**。x-show が一切効かず素 HTML が出るので「**枠は見えるが中身が空・ボタン全死**」になり、初見では「データが無い」と誤読しやすい(Console に `Alpine Expression Error: Invalid or unexpected token` + `Uncaught SyntaxError`)。
   直し方: **Alpine 式に生の `<` / `>` 比較を書かない**。`x-show="pinned.length > 0"` → `x-show="pinned.length"`(0 で falsy、等価)。比較が要るならメソッド化(`x-show="hasPinned()"`)するか `=== 0` 側で書く。block テーマ × Alpine inline 式 の組み合わせ固有。
   確認環境: mac wp-env(2026-06)/ 回帰: 手動(Console に `Alpine Expression Error` / `SyntaxError` が無い)

11. **[PIT-WP-ENV-002] wp-env のデフォルトポート 8888 が他プロジェクトと衝突 → `pnpm wp:start` が `port is already allocated`**
   直し方: `.wp-env.json` に `"port": 8899, "testsPort": 8902` 等を設定。**複数の Notion 風 WP を同時に立てるならポートは可変**(§4 の knob 候補)。
   確認環境: mac(2026-06。xserver-site-ops §6-5 でも再発=横展開済み)/ 回帰: 手動(衝突時にポート変更で復旧)


13. **[PIT-WP-JS-002] `type="module"` 化したハンドルに `wp_add_inline_script` / `wp_localize_script` が乗らない(★Phase 5 で実踏 2026-06-18)**
   `script_loader_tag` で `<script type="module">` に差し替えたハンドルへ `wp_add_inline_script(...,'before')` で nonce/config を渡しても、**フロントに `window.notionWP` が一切出力されない**(module 化でインライン付与が外れる)。`wp_localize_script` の文字列化(§6-1)とも二重に噛む。
   直し方: **`wp_head` で先に直接出力する**。`add_action('wp_head', fn() => print '<script>window.notionWP = '.wp_json_encode($cfg).';</script>', 5)`。module は defer 相当で遅延実行されるので、head で**素の(非 module)script として先に定義**すれば、後から走る module から確実に読める。`wp_json_encode` なら §6-1 の文字列化も同時に回避できる(数値は数値のまま)。
   確認環境: mac wp-env(2026-06-18)/ 回帰: 手動(フロントで `window.notionWP` が定義されている)

## 7. 固有スキル(ビルダー標準テンプレに無い。シードが同梱/参照)

- **`notion-migration`**: Notion → WordPress 移行。1 件で型 → 確認 → 本番一括。冪等・レート制限バックオフ・ブロック変換対応表(未対応はログ)。

## 8. ハーネス宣言(実体はビルダー templates/ が供給)

シードは宣言だけ。ハーネス本体はビルダーが焼く:

- 用途=Web → **標準デザイン基準 + design-review スキル**。`.claude/rules/design.md` に「Notion 風 UI の審美眼」を上書き(3カラム基本形=サイドバー/中央リスト/右パネル / 静かなトーン / 閲覧スライド・編集フェードの使い分け / 編集 UI は控えめ)
- 標準ハーネス一式(secrets / context-hygiene / hooks / self-heal / dashboard)はビルダーが配置
- **Phase ごとに design-review を 1 周**(§5)。self-heal は §6 の地雷を貯める器

## 9. 適応指示(環境差の吸収 + 安全側デフォルト + 個人データ剥離)★最重要

### 安全側デフォルト(柱1「事故らない」)
- **ローカル(wp-env)のみで完成まで進める**。公開・本番デプロイは**買い手が明示の合図を出してから**
- `.env` は `.env.example` からコピー。秘密の中身に触れない(`rules/secrets.md`)

### この完成プロジェクトの「kote2 固有」= ②で剥がす/買い手に聞く対象
| 固有データ | 出どころ | 置換 |
|---|---|---|
| kote2 のプロフィール一式 | `aboutme.md`(実物) | 空テンプレ → 買い手の必須2問 |
| 作者の本番 URL(非公開) | `.env`(`WP_SITE_URL`) | 空 → 公開時に買い手が設定 |
| 作者の本番構成(自宅サーバ + トンネル等) | `docker-compose.prod.yml` 等 | **同梱しない**(公開は買い手の選択) |
| AI 投稿連携(n8n MCP コネクタ) | 別案件で後付け | **このレシピに混ぜない**。`recipe-ai-posting` に切り出す |
| コレクション実データ(講座/知識) | CPT 実データ | 「あなたのコレクション」へ一般化 |
| 移行元 Notion の DB 構造 | kote2 の Notion | 買い手の Notion を聞く |
| ダーク既定(「白が眩しい」) | 作者の好み | knob 化(§4) |

## 10. 完成判定(買い手の AI が自己検証)

§1 機能構成表に対する **3 値判定**(一括の「全部緑」判定はしない。任意機能を OFF にすると構造的に満たせなくなるため、表の状態ごとに判定する):

- **required**(CORE-01〜03 / LAYOUT-01)= すべて **PASS**(1 つでも FAIL なら未完成)
- **optional-enabled** = enabled のものは PASS / disabled にしたものは **SKIP**
- **optional-disabled**(既定 FEAT-04)= 既定 **SKIP**(ON にしたなら PASS)
- **excluded**(EXCL-01)= 判定対象外

かつ §5 の各 Phase 検証が緑、`scripts/validate-output.sh` が PASS。
見た目は design-review を 1 周(スクショ → `design.md` 照合 → 修正)してから「完成」と言う。

### テストマトリクス(機械照合。auto 行は `scripts/recipe-test.sh` が実行)

| TEST ID | 対象 | 種別 | tier | 検証方法 | 期待値 |
|---|---|---|---|---|---|
| TEST-001 | — | auto | smoke | `curl -fsS -o /dev/null "http://localhost:${WP_PORT:-8888}/"` | ローカル WP のトップが 200 |
| TEST-002 | PIT-WP-REST-001 | auto | smoke | `curl -fsS -o /dev/null "http://localhost:${WP_PORT:-8888}/?rest_route=/wp/v2/posts"` | rest_route 形式で REST が 200 |
| TEST-003 | PIT-WP-REST-002 | auto | full | `curl -fsS -o /dev/null "http://localhost:${WP_PORT:-8888}/?rest_route=/wp/v2/posts&orderby=menu_order&order=asc"` | 400(rest_invalid_param)でなく 200 |
| TEST-004 | CORE-01 | manual | full | クリック遷移で全体再読込が起きない(DevTools Network で確認) | 差し替え遷移のみ |
| TEST-005 | CORE-02 | manual | full | ピーク=右 50% スライド / 編集=100% フェード iframe | 2 モードが混ざらない |
| TEST-006 | CORE-03 | manual | full | ドラッグ → REST 200 → リロード | 順序が DB に残る |
| TEST-007 | LAYOUT-01 | manual | full | トップで 3 カラム描画(2 ペイン選択時は 2 分割) | レイアウト骨格 |
| TEST-008 | FEAT-01 | manual | full | 非ログインで編集 UI が一切出ない | canEdit ゲート |
| TEST-009 | FEAT-05 | manual | full | 移行を 2 回実行 | 重複 0(冪等) |

<!-- ============================================================ -->
<!-- 詰める論点(CONCEPT §8 未決と対応):                               -->
<!--  - AI投稿連携は別レシピ recipe-ai-posting に分離(§9 で宣言済)     -->
<!--  - @pro-only 線引きの最終確認(§5/§6/§7 のフル実装をどこまで Pro に) -->
<!--  - Free strip 後に骨組みが独立して読めるかの確認                   -->
<!--  - 「一緒に作る(ライブ捕捉→仕上げ)」モードへの将来移行(CONCEPT §7) -->
<!--  - ③適応の射程: 同一スタック差し替え / 別スタック再実装の線引き     -->
<!-- ============================================================ -->

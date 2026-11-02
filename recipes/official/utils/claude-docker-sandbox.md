<!-- ============================================================ -->
<!-- recipe: claude-docker-sandbox — Claude Code を1フォルダに閉じ込める -->
<!-- 由来: claude-docker-sandbox-demo を実ビルドして結晶化(ライブ捕捉 → 結晶化)。-->
<!-- 状態: 実機で build → run → 隔離確認 → Dev Container + 拡張 GUI まで確認済み。-->
<!--                                                                        -->
<!-- ★固有値を焼かない: ドメイン / 実パス / 氏名 / メール / API キー / デプロイ先  -->
<!--   は本文に一切書かない。買い手ごとに変わる値は §9 の置換表に「何が要るか」だけ。 -->
<!-- ============================================================ -->

# claude-docker-sandbox — このフォルダだけを Claude Code の作業領域に閉じ込める

「PC の中の他のファイルに触らせず、**渡した1フォルダだけ**を Claude Code の作業場所にする」
サンドボックス(隔離された小部屋)を Docker で作る。非エンジニア向けの教材デモとしても使える。

- 製品名: フォルダ隔離サンドボックス
- 用途分類: 特殊(開発環境サンドボックスのデモ。最も近いのは自動化=開発ツール)
- 必要ビルダー VERSION: v3.8.0 以上
- 検証ステータス: `verified` — skeleton(骨組みのみ)/ experimental(実装したが未実証)/ verified(実ビルドで結晶化済み)。**verified だけが配布対象**
- 動作確認: `mac ✅` / `win ⬜` — 実機で建てて緑を取れた OS(⬜=未検証=動かない確証ではない)
- 配布元検証: `✅` — 配布元(kote2)が最終サインオフ(2026-08-03。official 配置=検証済みの運用)

---

## 1. これは何 / 機能構成 + 完成形(受け入れ基準)

### 機能構成(★ここだけが必須/任意/不採用を決める正本)

| ID | 機能 | 状態 | Phase | 完成判定 |
|---|---|---|---|---|
| CORE-01 | フォルダ単位の隔離(指定1フォルダだけを `/workspace` にマウント) | required | Phase 2 | PASS 必須 |
| CORE-02 | Claude Code 同梱のコンテナイメージ(Dockerfile) | required | Phase 1 | PASS 必須 |
| CORE-03 | ワンコマンド起動(ターミナル方式の `run-sandbox.sh`) | required | Phase 2 | PASS 必須 |
| FEAT-01 | docker compose 起動(別経路) | optional-enabled | Phase 3 | enabled なら PASS 必須 |
| FEAT-02 | Dev Container で VS Code ごと隔離(Reopen in Container) | optional-enabled | Phase 4 | enabled なら PASS 必須 |
| FEAT-03 | Dev Container にエディタ拡張 GUI を自動インストール(customizations) | optional-enabled | Phase 5 | enabled なら PASS 必須 |
| FEAT-04 | ログイン永続化(`~/.claude` を名前付きボリュームに保存) | optional-disabled | — | 既定 SKIP |
| FEAT-05 | 隔離確認デモスキル(中は見える/外は見えないを実演) | optional-enabled | Phase 6 | enabled なら PASS 必須 |
| EXCL-01 | ネットワーク遮断(許可先のみ通すファイアウォール) | excluded | — | 別レシピ/上級 |

### 完成形(受け入れ基準)
- [ ] required(CORE-01〜03)がすべて緑
- [ ] enabled な optional(FEAT-01/02/03/05)がすべて緑(FEAT-04 は disabled=SKIP)
- [ ] ローカルで「コンテナ内から `/workspace` は見え、ホストの他フォルダは見えない」が再現 ← ここまでが「完成」

---

## 2. スタック

| 層 | 採用 | 一行理由 |
|---|---|---|
| 隔離基盤 | Docker(Docker Desktop) | フォルダ単位の隔離が最も分かりやすく実演でき、公式 devcontainer の王道 |
| ベースイメージ | `node:20-bookworm-slim` | Claude Code が Node ランタイムを前提。slim で軽量 |
| CLI | `@anthropic-ai/claude-code`(コンテナ内に npm でグローバル導入) | コンテナ内グローバルは公式案内どおり npm を使う(プロジェクト依存は別) |
| 起動 | bash スクリプト + docker compose + devcontainer | ターミナル(主役)/ compose / VS Code の3経路を用意 |

---

## 3. 魔法のタネ(★変えるな。スタック非依存の本質)

- **隔離の本体は「持ち込むフォルダを1つに絞る」こと**。`docker run` で `-v <このフォルダ>:/workspace`
  のように**そのフォルダだけ**をマウントし、ホストの他の場所はマウントしない。これだけで
  コンテナ内の AI はホストの他ファイルに到達できなくなる(CORE-01)。
- **作業領域 = マウント1点**。`/workspace` の中はホストと同じ実体(双方向に反映)、外は別世界。
  「壊れてもこの中だけ」という安心感は、この1点マウントから生まれる。
- **起動は1コマンド**で完結させる(CORE-03)。非エンジニアが「黒い画面」に怯えないための要。

この3点を崩すと「ただのコンテナ」になり、サンドボックスとしての教材価値が消える。

---

## 4. 改変の余地(★変えていい。knob 3分類)

| 分類 | 中身 | 変えると |
|---|---|---|
| **軽量設定** | ベースイメージのタグ / 追加 apt パッケージ / コンテナ実行ユーザー名 / イメージ名 | 設計を変えずに差し替え可。サイレント適用してよい |
| **機能モジュール** | §1 表の optional-*:compose(FEAT-01)/ Dev Container(FEAT-02)/ 拡張自動入れ(FEAT-03)/ ログイン永続化(FEAT-04)/ デモスキル(FEAT-05) | Phase とテストが増減。§1 表の状態で ON/OFF |
| **派生アーキ** | 隔離方式そのものの差し替え(OS ネイティブ sandbox / 権限設定のみ / ファイアウォール版=EXCL-01) | **knob ではない**。魔法のタネ(1点マウントの思想)だけ移植して別実装=実質「別レシピ」。提案 → ユーザー GO |

---

## 5. 再現の順路(Phase + 検証)

1 Phase 作る → その場で検証(緑)→ 次へ。一気に作らない。

- **Phase 1 — コンテナイメージ(CORE-02)**: `Dockerfile` を作る(ベース Node 20 → git/curl →
  `npm i -g @anthropic-ai/claude-code` → 非 root の `node` ユーザー → `WORKDIR /workspace`)。
  検証(緑): `docker build` が成功する。
- **Phase 2 — ターミナル方式の隔離起動(CORE-03 + CORE-01)**: `run-sandbox.sh` を作る。中核は
  `docker run -it --rm -v "<このフォルダ>":/workspace -w /workspace ... bash`。Docker 未起動の事前チェックと、
  `.env` があれば `--env-file` で渡す分岐を入れる。
  検証(緑): スクリプト実行でコンテナ内シェルに入り、`ls /workspace` は中身が見え、`ls /Users` は空 = ホスト隔離。
- **Phase 3 — compose 起動(FEAT-01)**: `docker-compose.yml` に同じ1点マウントを定義。
  検証(緑): `docker compose run --rm sandbox` で Phase 2 と同じ隔離状態に入れる。
- **Phase 4 — Dev Container(FEAT-02)**: `.devcontainer/devcontainer.json` を作り、`workspaceMount` で
  そのフォルダだけを `/workspace` に。`--env-file .env` を使うので**起動前に `.env` の実在が必須**(§6)。
  検証(緑): 「Reopen in Container」でウィンドウがコンテナ表示になり、統合ターミナルがコンテナ内。
- **Phase 5 — 拡張 GUI を中で使う(FEAT-03)**: `customizations.vscode.extensions` にエディタ拡張 ID を追記。
  検証(緑): コンテナ作成時に拡張が中に入り、GUI が起動。コンテナは新環境なので `/login` でサインインし直す。
- **Phase 6 — 隔離確認デモ(FEAT-05)**: 「中は見える/外は見えない」を実演するスキルを置く(§7)。
  検証(緑): スキル起動で `/workspace` は見え、`/Users` 等ホスト領域は無いことを実コマンド結果で示せる。

> FEAT-04(ログイン永続化)は既定 SKIP。必要時のみ §9 の置換どおり名前付きボリュームを足す。

---

## 6. 固有の地雷 + 直し方

各地雷は固定 ID(`PIT-{ドメイン}-{3桁}`)+ 確認環境 + 回帰を持つ([templates/recipe/recipe-template.md](../templates/recipe/recipe-template.md) の PIT 規約)。

### [PIT-SHELL-002] `run-sandbox.sh` が `ENV_ARGS[@]: unbound variable` で落ちる
- 症状: ビルドは成功するのに `docker run` 直前で停止し、コンテナに入れない。
- 原因: macOS 標準 bash は 3.2 系。`set -u` 下で**空配列**を `"${ARR[@]}"` 展開すると「未定義」と判定される
  古い挙動(bash 4.4+ では起きない)。`.env` 無し時に env 用配列が空でここを踏む。
- 直し方: `"${ARR[@]}"` を `${ARR[@]+"${ARR[@]}"}` に変える(空なら何も展開しない安全イディオム)。なぜ効く=
  配列が未設定/空のときは展開自体をスキップするため nounset に触れない。
- 確認環境: mac bash 3.2 実機(2026-06)/ 回帰: TEST-003(§10 マトリクス。安全イディオムの存在)

### [PIT-DEVCON-001] Dev Container 起動が `--env-file .env` で失敗
- 症状: 「Reopen in Container」直後に env ファイルが見つからない系のエラーで起動しない。
- 原因: `runArgs` の `--env-file .env` は起動時にファイルの**実在**を要求する(値は空でも可)。
- 直し方: 入る前にホスト側で空の `.env` を用意(`.env.example` をコピー)。認証はコンテナ内で `/login`。
- 確認環境: mac 実機(2026-06)/ 回帰: 手動(README に「入る前に .env を用意」)

### [PIT-DEVCON-002] コンテナの中でエディタ拡張 GUI が出ない
- 症状: ターミナルの CLI は使えるのに、エディタ右パネルの GUI が現れない。
- 原因: エディタ拡張は**コンテナ側にインストールされたものだけ**動く。素の `docker run`(ターミナル方式)では
  原理的に届かず、Dev Container でも `customizations` に書かないと中へ入らない。
- 直し方: ターミナル方式なら CLI で使う(これで十分)。GUI を中で使いたいなら Dev Container にして
  `customizations.vscode.extensions` に拡張 ID を追記(または拡張マーケットの「コンテナにインストール」)。
- 確認環境: mac 実機(2026-06)/ 回帰: 手動(FEAT-03 有効時に拡張が中に入る)

### [PIT-CC-LOGIN-001] コンテナ内で使えるモデルが最小構成だけになる
- 症状: モデル選択に下位モデルしか出ない。
- 原因: コンテナは新環境=未ログイン。ログイン前は選択肢が絞られる。
- 直し方: コンテナ内で `/login`。表示モデルは契約プランに依存(プラン制限なら API キー方式で全モデル可)。
- 確認環境: mac 実機(2026-06)/ 回帰: 手動(手順書に「新環境=要 /login」を明記)

---

## 7. 固有スキル / 道具

- **隔離確認デモスキル(FEAT-05)**: 「中か/`/workspace` は見える/外は見えない」を実コマンドで示すツアー型スキル。
  破壊系は使わず**見る系コマンドだけ**で隔離を証明する。教材の「おぉ」を作る主役。実装全文は @pro-only。

---

## 8. ハーネス宣言

用途の標準一式を `templates/` から焼く(共通生成ファイル + 自己修復 hooks + rules)。固有の上書きは下記。

- 標準一式: CLAUDE.md / README.md / AGENTS.md / dashboard.html / output-style / commands(self-heal 等)
- ルール: `../templates/rules-secrets.md`(API キーを扱うため必須)/ `../templates/rules-context-hygiene.md`
- 口調: `../templates/output-style-default.md`
- 固有上書き: `Dockerfile` / `run-sandbox.sh` / `docker-compose.yml` / `.devcontainer/devcontainer.json` /
  隔離確認デモスキル
- 完了前の機械チェック: `scripts/validate-output.sh`

---

## 9. 適応指示(環境差・安全側・固有値)

- **安全側デフォルト**: ローカルのみで完成まで。ネットワーク遮断版(EXCL-01)は上級者の明示要望時だけ。
- **OS 差**: 自己修復 hooks と `run-sandbox.sh` は macOS / Linux 前提。Windows は hooks 非配置 +
  起動は Dev Container か手動 `docker run` を案内。
- **固有値の置換(★実値は焼かない)**:

| 置き場 | 何の値か | 既定 |
|---|---|---|
| マウント元フォルダ | 隔離したい作業フォルダ | スクリプトが自分の置かれたフォルダを採用(買い手は別フォルダにコピーして使える) |
| `ANTHROPIC_API_KEY` | Claude の合鍵(API キー方式の時) | 空。買い手が手で記入、または `/login` |
| イメージ名 | コンテナイメージの名前 | 任意の汎用名(固有名を焼かない) |
| 拡張 ID | エディタ拡張の Identifier | 拡張ページの Identifier を買い手が確認して記入 |

---

## 10. 完成判定(買い手の AI が自己検証)

§1 機能構成表に対し:
- required(CORE-01〜03)= すべて **PASS**(1 つでも FAIL なら未完成)
- optional-enabled(FEAT-01/02/03/05)= enabled のものは PASS / disabled にしたものは SKIP
- optional-disabled(FEAT-04)= 既定 **SKIP**(ON にしたなら PASS)

かつ `scripts/validate-output.sh` が PASS、§5 各 Phase の検証が緑であること。

### テストマトリクス(機械照合。auto 行は `scripts/recipe-test.sh` が実行)

auto 行は生成スモーク(Docker 実行が要るものは manual)。

| TEST ID | 対象 | 種別 | tier | 検証方法 | 期待値 |
|---|---|---|---|---|---|
| TEST-001 | CORE-02 | auto | smoke | `test -f Dockerfile` | イメージ定義がある |
| TEST-002 | CORE-03 | auto | smoke | `test -f run-sandbox.sh && bash -n run-sandbox.sh` | 起動スクリプトの構文 OK |
| TEST-003 | PIT-SHELL-002 | auto | smoke | `grep -qF "[@]+" run-sandbox.sh` | 空配列の安全イディオムが入っている |
| TEST-004 | FEAT-01 | auto | smoke | `test -f docker-compose.yml` | compose 経路がある |
| TEST-005 | FEAT-02 | auto | smoke | `test -f .devcontainer/devcontainer.json` | Dev Container 経路がある |
| TEST-006 | CORE-01 | manual | full | コンテナ内で `ls /workspace`(中身あり)/ `ls /Users`(空) | 1 点マウント隔離 |
| TEST-007 | FEAT-05 | manual | full | 隔離確認デモスキルのツアー | 「中は見える/外は見えない」を実演 |

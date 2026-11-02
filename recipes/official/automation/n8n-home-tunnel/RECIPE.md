<!-- ============================================================ -->
<!-- n8n-home-tunnel/RECIPE.md — 手元の n8n を専用トンネルで自分のドメインに公開する共有レシピ(パッケージ v2) -->
<!-- 由来: 通常生成した n8n 環境の実ビルド(mac 2026-09-25。setup → オーナー作成 → 公開 → MCP 接続まで実走)からの結晶化。 -->
<!--       設計判断は recipe/draft.md、地雷は SKILL.md の「ハマりどころ」と実走の記録から起こした。 -->
<!-- 状態: required + optional-enabled を mac(2026-09-25)と Windows(2026-09-25・パッケージから再生)で実ビルドして緑。FEAT-02 / FEAT-03 は両方とも未実走 -->
<!-- v2: 機械メタ(製品名 / 用途 / 検証 3 軸)は recipe.json。スクリプト一式は templates/core、検査は tests/ -->
<!-- ★固有値を焼かない: ドメイン・ホスト名・トンネル名・MCP 名・コンテナ名・ボリューム名・ポートは -->
<!--   すべて {{PLACEHOLDER}} → 生成物の .env だけに入る。スクリプト・compose・スキルには直書きしない(TEST-002)。 -->
<!-- ★マシン別・ユーザー別が前提: 1 台 = 1 生成物 = 1 組の値。同じ人の 2 台目も「別の値で別に建てる」(§3-1 / §9)。 -->
<!-- ============================================================ -->

# n8n-home-tunnel — 自宅 n8n 公開キット(手元の Docker の n8n を、マシン専用のトンネルで自分のドメインに公開)

## 1. これは何 / 機能構成 + 完成形(受け入れ基準)

手元の PC(Mac / Windows)の Docker で n8n を動かし、Cloudflare の**名前付きトンネル**で `https://{このマシン専用のサブドメイン}/` として公開する。ルーターのポート開放は要らず、URL が固定なので Webhook の教材にも日常の自動化にも使える。Claude Code からは n8n 内蔵の MCP で「ワークフローを作って / 直して / 試して」と話しかけて直接操作できる。

**前提は「マシン別・ユーザー別」**。同じ人が Mac と Windows の両方に建てる時も、別の人が自分のドメインで建てる時も、**1 台ごとに別の名前・別のトンネル・別のデータ**で建てる。値はすべて生成物の `.env` に集まり、スクリプトは値を持たない。

### 機能構成(★ここだけが必須/任意/不採用を決める正本)

| ID | 機能 | 状態 | Phase | 完成判定 |
|---|---|---|---|---|
| CORE-01 | マシン専用の n8n: 公式イメージ・版固定・`127.0.0.1` だけで待ち受け・名前付きボリューム。コンテナ名 / ボリューム名 / ポート / 版はすべて `.env` から読む | required | Phase 1 | PASS 必須 |
| CORE-02 | マシン専用の名前付きトンネル + DNS: `setup.sh` が作る。既存の cloudflared 設定を読まない(常に `--config`)・DNS を上書きしない・他のマシンで作ったトンネルを使い回さない | required | Phase 1 | PASS 必須 |
| CORE-03 | オーナー作成ゲート: n8n のオーナー未作成ならトンネルを起動しない(`up.sh`) | required | Phase 2 | PASS 必須 |
| CORE-04 | 運用スクリプト `setup` / `up` / `down` / `status` + スキル `n8n-env`(話しかけて起動・停止・点検) | required | Phase 2 | PASS 必須 |
| FEAT-01 | Claude Code から MCP で直接操作: `setup.sh` が `.env` の `MCP_NAME` と `N8N_HOST` から `.mcp.json` を作る(OAuth。合鍵をファイルに書かない) | optional-enabled | Phase 4 | enabled なら PASS 必須 |
| FEAT-02 | ワークフローの書き出し・読み込み(REST API・`wf.mjs`。配布用 JSON を `workflows/` に)。**未検証** | optional-disabled | Phase 5 | 既定 SKIP |
| FEAT-03 | 片付け `teardown.sh`(停止 → トンネル削除 → 希望すればデータ削除 → DNS 削除の案内)。一時利用のマシン向け。**未実走** | optional-disabled | Phase 5 | 既定 SKIP |
| EXCL-01 | 再起動後の自動起動(launchd / タスクスケジューラ) | excluded | — | 別レシピ |
| EXCL-02 | Postgres・キューモードなどの本番向け構成 | excluded | — | 別レシピ |
| EXCL-03 | quick tunnel(一時 URL。毎回 URL が変わり Webhook に向かない) | excluded | — | 使わない |
| EXCL-04 | Cloudflare Access での編集画面の保護(Webhook の経路と分けて設計が要る) | excluded | — | 別レシピ |

### 完成形(受け入れ基準)

- [ ] required の機能がすべて緑
- [ ] enabled な optional がすべて緑(disabled は SKIP = 欠落ではない)
- [ ] ローカルで n8n が動き、オーナー作成後に公開 URL が n8n を返す ← ここまでが「完成」。公開(トンネル起動)は §9 の「公開の合図」から

## 2. スタック

| 層 | 採用 | 備考 |
|---|---|---|
| 実行 | n8n 公式 Docker イメージ(`docker.n8n.io/n8nio/n8n`)+ Docker Compose | 版は `.env` の `N8N_VERSION` で固定。再生時点の最新安定版を確認して入れる(2.40.6 で確認) |
| 公開 | cloudflared の名前付きトンネル + Cloudflare 管理下のドメイン | 2026.7.2 で確認。Mac は `brew`、Windows は `winget` |
| 運用 | bash スクリプト(`scripts/`) | Windows は Git Bash で実行(Claude Code に同梱) |
| AI 操作 | n8n 内蔵 MCP(n8n 2.13 以降で作成・編集可)+ Claude Code の `.mcp.json` | 共通ノウハウは `knowledge/n8n.md` |
| 配布用の出し入れ | Node.js 20 以上(`node --env-file`)+ n8n REST API | FEAT-02 の時だけ |

## 3. 魔法のタネ ★変えるな

1. **1 台 = 1 組**。公開ホスト名・トンネル名・MCP 名・コンテナ名・ボリューム名・ポートは台ごとに別。同じトンネルを 2 台で動かすと、Cloudflare がアクセスを 2 台に振り分けてしまう(どちらに届くか分からない)。2 台目は「コピー」ではなく「別の値で新しく建てる」。
2. **値は `.env` だけに持ち、スクリプトは値を持たない**。compose・スクリプト・スキルに固有値を 1 つも書かない(TEST-002 で検査)。だから同じテンプレートがどのマシン・どの人でもそのまま使える。
3. **既存の cloudflared 設定を信用しない**。`~/.cloudflared/config.yml` には昔のトンネルや他のマシンと同じトンネルが残っていることがある。起動も管理コマンドも必ず `--config` でプロジェクト内の設定を指定する(PIT-CFTUNNEL-003 / 004)。
4. **何も上書きしない**。DNS は上書きしない(使用中なら止まって別名を相談)。他のマシンで作った同名トンネルは使い回さない(認証ファイルが無ければ止まる)。`setup.sh` は何回実行しても安全。
5. **オーナーを作るまで公開しない**。n8n は最初に画面を開いた人がオーナーになれる。オーナー作成は `127.0.0.1` で済ませ、確認できてからトンネルを起動する(CORE-03)。
6. **秘密は画面にもチャットにも出さない**。暗号化キーは `setup.sh` が生成して `.env` に書くだけ。API キーは本人が `.env` に貼る。MCP は OAuth なので `.mcp.json` に合鍵が入らない。

## 4. 改変の余地 ★変えていい

| 分類 | 中身 | 既定 |
|---|---|---|
| 軽量設定 | 公開ホスト名・トンネル名・MCP 名・コンテナ名・ボリューム名・ポート・n8n の版(すべて §9 の置換表の値) | §9 の命名規則 |
| 軽量設定 | タイムゾーン(compose の `GENERIC_TIMEZONE` / `TZ`) | `Asia/Tokyo` |
| 機能モジュール | FEAT-01(MCP)を外す / FEAT-02(書き出し・読み込み)・FEAT-03(片付け)を入れる | FEAT-01 のみ ON。一時利用のマシンでは FEAT-03 を ON にするのがおすすめ |
| 派生アーキ | Docker を使わない(npm で直接インストール)/ トンネルの代わりにポート開放やリバースプロキシ / n8n Cloud | knob ではない。§3 の 1〜6 だけ移植して別レシピ |

## 5. 再現の順路(Phase + 検証)

- **Phase 0 土台**: Docker Desktop(起動しておく)・cloudflared・(FEAT-02 の時)Node.js 20 以上。Cloudflare でドメインを管理していること。環境の入れ方は README に書く
  - 検証: `docker info` が通る / `cloudflared --version` が出る
- **Phase 1 テンプレートを写して値を入れる(CORE-01 / CORE-02)**: `recipe.json` の `templates.core` を `to` へコピー → `.env.example` の `{{...}}` を §9 の置換表の値で埋める(**このマシンの値**。他のマシンの値を使い回さない)→ `bash scripts/setup.sh`(`.env` 作成 → 暗号化キー生成 → トンネル作成 → DNS 登録 → トンネル設定 → `.mcp.json`)
  - 検証: TEST-001 / 002 / 003 が PASS。`setup.sh` をもう一度実行して「作成済み」だけが並ぶ
- **Phase 2 起動(CORE-03 / CORE-04)**: `bash scripts/up.sh`(1 回目は n8n だけ起動して公開しない)→ ユーザーが `http://127.0.0.1:{N8N_LOCAL_PORT}` でオーナーを作成
  - 検証: TEST-004 が PASS。TEST-005(未作成なら「まだ公開していません」で止まる)
- **Phase 3 公開(CORE-02)**: §9 の公開の合図が出てから、オーナー作成後に `bash scripts/up.sh`(2 回目)でトンネル起動
  - 検証: TEST-006 が PASS(公開 URL の本文が n8n の healthz)
- **Phase 4 MCP(FEAT-01 が enabled の時)**: ユーザーが n8n の Settings → Instance-level MCP → Enable(「Expose all workflows」)→ Claude Code を開き直して `.mcp.json` のサーバーを許可 → `/mcp` で Authenticate
  - 検証: TEST-007 が PASS(401 = 有効)/ TEST-008(Claude Code からテスト用ワークフローを作ってテスト実行)
- **Phase 5 任意機能**: FEAT-02 が enabled なら `.env` に API キー → TEST-009。FEAT-03 が enabled なら `teardown.sh` を同梱し README に片付け手順 → TEST-010。disabled の機能は該当ファイル(`wf.mjs` / `teardown.sh`)とスキルの該当節を外す

## 6. 固有の地雷 + 直し方

1. **[PIT-CFTUNNEL-003] 既存の `~/.cloudflared/config.yml` を読んで、別のトンネルが動く / 全部 404 になる**
   症状: `cloudflared tunnel ... run` や quick tunnel が、意図しないトンネルを起動する・公開 URL が 404。原因: `--config` を付けないと cloudflared は既定の置き場(`~/.cloudflared/config.yml` や Homebrew の `etc/cloudflared/`)の設定を読む。昔のトンネルや、他のマシンと同じトンネル ID が残っていることがある。直し方: 起動・管理コマンドはすべて `--config` でプロジェクト内の設定を明示する。古い設定は消さずに名前を変えて退避する
   確認環境: mac cloudflared 2026.7(2026-05 quick tunnel の 404 / 2026-09 本レシピで他マシンと同じ ID の設定を発見)/ 回帰: TEST-003
2. **[PIT-CFTUNNEL-004] 既存設定を避けるつもりの `--config /dev/null` が「設定が空」エラーになる**
   症状: `cloudflared tunnel --config /dev/null list` が `Configuration file /dev/null was empty` をエラーで出す(結果は返るので紛らわしい)。原因: cloudflared は空の設定ファイルをエラー扱いにする。直し方: 中身 1 行だけのダミー `cloudflared/admin.yml`(`no-autoupdate: true`)を管理コマンドの `--config` に渡す
   確認環境: mac cloudflared 2026.7(2026-09)/ 回帰: TEST-003
3. **[PIT-CFTUNNEL-005] ドメインにワイルドカード DNS があると、外から名前の空きを判定できない**
   症状: どのサブドメインを `dig` しても Cloudflare の IP が返り、「使用中」に見える。原因: `*.{ドメイン}` のワイルドカードレコード。直し方: 事前判定はあきらめ、`cloudflared tunnel route dns` を**上書きなし**で実行する。明示レコードと衝突したらそこで止まるので、別名を相談する(`--overwrite-dns` は使わない)。登録結果の表示が `{ホスト名} is already configured` か `CNAME {ホスト名} ` であることまで確認する(ログインしたドメインが違うと「ホスト名.別ドメイン」で登録されるため)
   確認環境: mac(2026-09。ワイルドカード応答を確認。明示レコードとの衝突での停止は未再現)/ 回帰: TEST-003
4. **[PIT-N8N-001] healthz が 200 になった直後は `/rest/settings` がまだ応答しない**
   症状: 起動直後のオーナー作成判定が「確認できません」になる。原因: n8n は healthz を先に返し、REST API の準備が数秒遅れる。直し方: 2 秒おきに最大 30 秒リトライし、判定できないうちは公開しない側に倒す
   確認環境: mac n8n 2.40.6(2026-09)/ 回帰: 手動(TEST-005 の初回起動で「確認できません」が出ない)
5. **[PIT-N8N-002] MCP の URL `https://{ホスト}/mcp-server/http` が 404**
   症状: Claude Code の MCP 接続が失敗する。原因: n8n の設定で MCP を有効にしていない(有効化すると認証待ちの 401 に変わる)。直し方: Settings → Instance-level MCP → Enable MCP access
   確認環境: mac n8n 2.40.6(2026-09)/ 回帰: TEST-007

## 7. 固有スキル / 道具

- **スキル `n8n-env`**(`templates/core/skills/n8n-env/SKILL.md`): 起動・停止・点検・MCP での操作・出し入れ・更新・片付けの手順。値は `.env` から読む前提で書かれている
- **`scripts/_env.sh`**: 全スクリプト共通の下ごしらえ(`.env` の読み込み・必須値の検査・オーナー判定・Windows のパス変換・`.mcp.json` の書き出し)
- **`cloudflared/admin.yml`**: 管理コマンドに既存設定を読ませないためのダミー(PIT-CFTUNNEL-004)
- 生成 CLAUDE.md の「守ること」に入れる: 他のマシン・他の n8n のトンネル / コンテナ / ボリュームに触らない、cloudflared は常に `--config`、DNS を上書きしない、オーナー未作成で公開しない、`N8N_ENCRYPTION_KEY` を変えない、公開・削除・版の変更は明示の OK の後
- 生成 CLAUDE.md の「できること」に入れる: n8n 起動して / 止めて / 状態見せて / こういうワークフローを作って(FEAT-01)/ 講座用に書き出して(FEAT-02)/ 片付けて(FEAT-03)

## 8. ハーネス宣言

- 用途の標準一式(`usecase/automation.md`)を `templates/` から焼く: CLAUDE.md / README.md + README.html / AGENTS.md(両対応時)/ dashboard.html / `.claude/`(settings・hooks・commands・rules の secrets と context-hygiene)/ `.project-memory/`
- `.claude/settings.json` の deny に `Read(~/.cloudflared/**)` を足す(トンネルの認証ファイル)。ask に `Bash(bash scripts/teardown.sh:*)` / `Bash(docker volume rm:*)` / `Bash(docker compose down -v:*)` を足す
- `recipe/`(レシピ追跡)は作らない(このレシピから建てた生成物の変更は、このレシピの更新モードで戻す)
- `recipe.json` の `templates.core` を写す。`gitignore` → `.gitignore`、`env.example` → `.env.example`(ファイル名の先頭の点は配布で落ちやすいので、パッケージ内では点なしで持つ)

## 9. 適応指示

### 値は 2 層で聞く(マシン別・ユーザー別)

**ユーザー別(その人に 1 つ。同じ人の 2 台目では聞き直さず確認だけ)**

| 聞くこと | 使い道 | 例 |
|---|---|---|
| Cloudflare で管理している自分のドメイン | 公開ホスト名の後ろ半分 | `example.com` |
| 用途の短い名前 | 名前の真ん中(省略可) | `note`(講座用)/ 無し |

**マシン別(1 台ごとに必ず聞く。前の台の値を使い回さない)**

| 聞くこと | 使い道 | 例 |
|---|---|---|
| このマシンの短い呼び名 | 名前の最後 | `mini` / `win` / `imac` |

### 置換表(`.env.example` の `{{...}}`)

既定は下の**命名規則**で組み立てて見せ、ユーザーが上書きしてよい(`MCP_NAME` など、呼びやすい名前を指定されたらそれに従う)。

| プレースホルダ | 中身 | 命名規則(既定) | 例(マシン「win」) |
|---|---|---|---|
| `{{N8N_HOST}}` | 公開ホスト名 | `n8n-{用途}-{呼び名}.{ドメイン}` | `n8n-note-win.example.com` |
| `{{TUNNEL_NAME}}` | Cloudflare 上のトンネル名 | `n8n-{用途}-{呼び名}` | `n8n-note-win` |
| `{{MCP_NAME}}` | Claude Code の MCP サーバー名 | `n8n-{呼び名}` | `win-n8n`(ユーザー指定) |
| `{{N8N_INSTANCE}}` | コンテナ名(Compose のプロジェクト名にも使う) | 生成プロジェクトのフォルダ名 | `n8n-win` |
| `{{N8N_VOLUME}}` | データのボリューム名 | `{N8N_INSTANCE の - を _ に}_data` | `n8n_win_data` |
| `{{N8N_LOCAL_PORT}}` | 手元の待ち受けポート | 5679 から順に、**このマシンで空いている**番号 | `5679` |
| `{{N8N_VERSION}}` | n8n の版 | 再生時点の最新安定版(https://github.com/n8n-io/n8n/releases) | `2.40.6` |

### 生成前に確かめること(このマシンで)

- **名前の重複**: `docker ps -a` / `docker volume ls` に同じコンテナ名・ボリューム名が無いか。同じマシンを別の人(別の OS アカウント)が使う時も Docker は共有なので重ねない
- **ポート**: `N8N_LOCAL_PORT` が空いているか(Mac: `lsof -iTCP:{PORT} -sTCP:LISTEN` / Windows: `netstat -ano`)
- **トンネル名**: 同じ Cloudflare アカウントに同名のトンネルがあれば、それは**他のマシンのもの**。使い回さず別名にする(`setup.sh` も認証ファイルが無ければ止まる)
- **既存の cloudflared 設定**: `~/.cloudflared/config.yml` があれば、このプロジェクトは読まないので壊さない。気になる時はユーザーの許可を得て名前を変えて退避する(PIT-CFTUNNEL-003)

### 安全側デフォルト

- **公開の合図**: Phase 1(トンネル作成と DNS 登録)は外向きの操作なので、設計書の OK をもって実行してよいが、**トンネルの起動(Phase 3)はオーナー作成後**。ゲートを迂回しない
- 暗号化キーはスクリプトが生成し、AI は `.env` を読まない。API キー・n8n のパスワードをチャットで受け取らない
- `teardown.sh`(FEAT-03)はユーザーが黒い画面で実行する(対話式・取り消せない)

### Windows(2026-09-25 実走済み: cloudflared 2026.9.3・n8n 2.40.7・Git Bash)

- Docker Desktop(WSL2)・`winget install --id Cloudflare.cloudflared`・Node.js 20 以上。スクリプトは Git Bash で実行(PowerShell / cmd では動かない)
- `winget` で cloudflared を入れた直後のシェルでは PATH に載っていないことがある → 黒い画面を開き直す(その場でなら `export PATH="/c/Program Files (x86)/cloudflared:$PATH"`)
- 初回の `setup.sh` は Cloudflare へのログインでブラウザが開く。公開 URL のドメインを選んで許可するよう案内する
- `cloudflared.exe` は Git Bash 形式のパス(`/c/...` で始まる)を読めないので、`setup.sh` はトンネル設定に書く認証ファイルのパスだけ `cygpath -m` で変換する(`_env.sh` の `native_path`)
- 確認済み: Git Bash から起動した `cloudflared.exe` を `kill` で止められる(`down.sh` → `up.sh` の 1 往復でデータも残る)/ OneDrive 配下でも今回の範囲では動いた(それでも `knowledge/windows.md` の PIT-WIN-ONEDRIVE-001 のとおり、プロジェクトは OneDrive の外に置くのが無難)

## 10. 完成判定(買い手の AI が自己検証)

§1 機能構成表に対し:
- required = すべて PASS(1 つでも FAIL なら未完成)
- optional-enabled = enabled のものは PASS / disabled にしたものは SKIP
- optional-disabled = 既定 SKIP(ON にしたなら PASS)
かつ `scripts/validate-output.sh` が PASS、§5 各 Phase の検証が緑。

| TEST ID | 対象 | 種別 | tier | 検証方法 | 期待値 |
|---|---|---|---|---|---|
| TEST-001 | CORE-01 | auto | smoke | `bash recipe-tests/check-static.sh` | 必要なファイル・構文・`{{...}}` の置き忘れ無し・`.gitignore`・127.0.0.1 待ち受け・compose 展開が PASS |
| TEST-002 | CORE-04 | auto | smoke | `bash recipe-tests/check-per-machine.sh` | マシン別の値がスクリプト等に直書きされておらず、2 台ぶんの値で別々の `.mcp.json` ができる |
| TEST-003 | PIT-CFTUNNEL-003 | auto | smoke | `bash recipe-tests/check-cloudflared-guard.sh` | cloudflared は常に `--config`・`/dev/null` と `--overwrite-dns` を使わない |
| TEST-004 | CORE-01 | auto | full | `bash recipe-tests/check-live.sh local` | 手元の healthz が n8n の応答 |
| TEST-005 | CORE-03 | manual | full | オーナー作成前に `bash scripts/up.sh` | 「まだ公開していません」で止まり、トンネルを起動しない。作成後の 2 回目で公開される |
| TEST-006 | CORE-02 | auto | full | `bash recipe-tests/check-live.sh public` | 公開 URL の本文が n8n の healthz(別サービスではない) |
| TEST-007 | FEAT-01 | auto | full | `bash recipe-tests/check-live.sh mcp` | MCP の入口が 401(有効・認証待ち) |
| TEST-008 | FEAT-01 | manual | full | Claude Code で `/mcp` → Authenticate →「テスト用のワークフローを作ってテスト実行して」 | 作成とテスト実行ができ、n8n の画面にも出る |
| TEST-009 | FEAT-02 | manual | full | `wf.mjs list` → `export` → `import` | 書き出した JSON を読み込むと停止状態の同じワークフローができる |
| TEST-010 | FEAT-03 | manual | full | `bash scripts/teardown.sh`(トンネル名を入力) | トンネル一覧から消え、案内どおり DNS を消すと公開 URL が応答しなくなる |

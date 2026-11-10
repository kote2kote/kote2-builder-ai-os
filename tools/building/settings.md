# AI別の設定と権限

AIの入口・設定を追加/変更する時に読む。共通手順 `agent-settings@1`。2026-11-07にClaude公式資料を照合した雛形で、全環境での実効設定の検証済み印ではない。既存案件は独自設定を残して差分を確認し、ファイル全体を雛形で上書きしない。ホーム設定・認証は変更しない。

## Claude Code

- 案件の `CLAUDE.md` は共通 `AGENTS.md` を参照する薄い入口。設定候補の実物は [claude-settings.json](templates/claude-settings.json) → 案件 `.claude/settings.json`。ローカル設定や管理者設定の内容を秘密ごと収集しない。対象案件で読み込まれた設定と警告を確認する。
- 親の作業場 `.claude/settings.json` と案件の雛形は同じdeny/askを持つ。親の `autoMemoryEnabled: false` は保持する。共有設定は起動場所に依存するので、親または案件のルートから開始する。親で子の設定が自動適用される、子で親の設定を自動継承する、とは仮定しない。
- 共通設定にsandboxブロックは置かない。Windowsネイティブを含む両OSで共通のRead/Edit deny・危険Git操作のdeny・push/publish等のaskを使う。sandboxを無効にする指定も配らず、利用者・管理者が選んだ隔離設定を共通設定で解除しない。Bash等の別経路の秘密アクセス制限は、共通ルールだけでは保証しない。
- `Read(**/.env)`などの相対規則で、直下と子フォルダの既知の秘密ファイルを対象にする。`.env.example`も例外にせず、秘密のない例は別名で用意する。任意のファイル名や環境変数をすべて判別する仕組みではない。追加の認証ファイルは秘密の本文を読まず種別を確認して禁止候補へ加える。
- hooksやallow、MCP、サンドボックス解除を標準で足さない。必要なら目的・実行コード・通信先・発火条件・対応OS・失敗時の動作を別途検証して了承を得る。Bashは `Bash(git push *)` 形式に統一する。現在の公式仕様では末尾の `:*` と同等で、書式変更だけを安全性向上とは扱わない。
- `/status` の設定ソース、`/permissions` の規則と権限モード、起動警告を確認する。denyはask/allowより先に評価され、規則の配列は複数の設定元から合わさる。利用者の追加設定を消して合格させない。設定ソースが表示されても、すべての経路を実効確認したことにはならない。

### macOS・Linux・WSL2で任意に隔離を有効にする

有効化したい利用者は [claude-sandbox-settings.json](templates/claude-sandbox-settings.json) を設定例として使う。このファイルは自動読込されない。親OSなら親のルート、案件を単独起動するなら案件のルートの `.claude/settings.local.json` に、内容を確認してsandboxブロックを追加する。ファイルがなければ作成できるが、既存ファイルがあれば丸ごとコピーせず、既存のキー・配列・hooks等を保持して差分を示す。既存sandboxとの競合や管理者の強制設定は勝手に解除しない。local設定はGit共有・OS更新の対象外とする。

この例は `enabled:true`・`failIfUnavailable:true`・`autoAllowBashIfSandboxed:false`・`allowUnsandboxedCommands:false` と、従来の秘密パス/環境変数denyを維持する。利用者が選んだ隔離を利用できない時は停止する。例には、OSの更新の確認・取得に使う通信先 `github.com` と `api.github.com` だけをあらかじめ許可する指定（`network.allowedDomains`）が入っている。これを外すと、更新の確認のたびに通信の許可を聞かれるか、確認できずに止まる（止まっても安全で、本人のターミナルから確認できる。[更新の手順](../os-update.md)）。4.5.1以前にこの例を有効化した利用者のlocal設定は、OS更新では変わらない。通信先の許可を足すかどうかは本人が選び、AIは変更案を見せて了承を得てから足す。sandboxを無効にする・sandboxの外で実行する・TLS検証を省く、といった変更はしない。Linux/WSL2ではbubblewrapとsocat等の依存を確認する。依存ソフトを勝手にインストールしない。有効化後は新しい会話で `/sandbox`・`/status`・`/permissions` を確認し、架空データで通常の制作と拒否を試す。

Windowsネイティブにはこの例を有効化しない。Claude Codeのsandboxが必要ならWSL2で実行する。MacとWindowsで同じ案件を同期する時もlocal設定を同期しない。上位のuser/管理者設定がsandboxを強制していれば、共通設定からの分離だけでは起動問題を解消しない。設定元と対応策を示し、管理者設定や本人の選択を無断で変更しない。

### 4.4.0以前からの更新と既存案件

標準のままの共通sandboxは、通常のOS更新の差分・本人の確認を経て共通設定から外す。既存の追加設定は旧標準との比較で保持し、sandboxの独自変更や未解決の競合は上書きせず停止する。引き続き隔離を使う利用者には、適用前に上のlocal設定への移設案を示し、了承後に行う。確認の窓や次のOKを省略しない。

既存案件のsettings.jsonやlocal設定はOS更新で一斉に書き換えない。案件ごとに旧sandbox・共通deny/ask・独自設定・起動元を確認し、必要なブロックだけの変更案を示す。親だけの修正を案件にも適用済みと扱わない。新規生成時は共通雛形だけを配置し、任意例をsettings.jsonやlocal設定へ自動で混ぜない。

## Codex

- 共通入口は `AGENTS.md`。設定候補の実物は [codex-config.toml](templates/codex-config.toml) → 案件 `.codex/config.toml`。`on-request`・公式permission profile（`:workspace`を継承）・シェル通信無効を出発点とし、モデルや認証は指定しない。グローバル設定・認証ファイルへ書かない。
- project設定は信頼済み案件でのみ読み込まれる。起動時の実効設定・承認方式・書込範囲・通信可否を確認する。CLIやホストの上位設定が優先する場合がある。T3などのホストが別の権限を使う時に、雛形が強制すると説明しない。
- 親と新規案件には同じ標準の `.codex/config.toml` を同梱する。親から開始しただけでは、子の案件設定は適用されない。旧 `workspace-write` だけでは読取禁止にならない。新profileは秘密パスのdenyを追加するが、上位/CLIの旧sandbox指定があると旧方式が優先される。`on-request`でも許可範囲内の読取やコマンドは毎回確認されるとは限らない。
- Web検索も通信であり、シェル通信無効だけで無通信を保証しない。雛形では検索も無効。必要な公式資料の取得は利用環境の許可に従い、本人へ通信が必要なことを説明する。資料取得のために案件をfull-accessへ変えない。
- `python3 tools/building_check.py --project projects/<名前>` によるCodex設定検査にはPython 3.11以上が必須（標準ライブラリ `tomllib` を使用）。静的検査が通っても、案件の信頼状態やホストが採用した実効設定は別に確認する。

## 共通の限界

ClaudeのRead denyは組込みの読取や認識される一部のBashファイル操作に適用されるが、Python等の間接読取やMCP全体を遮断するものではない。Bashの先頭を指定する規則も、オプションの置き方・別コマンド・別ツールまで網羅しない。Codexの案件設定もClaudeのRead denyと同じ保護ではない。静的検査は実行時の承認・権限を強制しない。厳密な隔離が必要なら実行環境/OS権限を別途設計する。設定ファイルが存在する、構文が通る、実際に適用された、の3つを分ける。

実効確認は架空の秘密だけを置いた使い捨て環境で行う。CLI版・起動場所（親/案件）・権限モード・設定ソースを記録し、直下/子の秘密の直接読取、別経路、秘密でない文書の読取と編集を分けて確認する。通常HOME・既存の認証やカスタム設定を変更しない。隔離と認証を安全に両立できなければ試験を止め、その経路は「未確認」とする。禁止された読取を実データの別経路でやり直さない。

公式根拠: [Claude settings](https://code.claude.com/docs/en/settings)・[permissions](https://code.claude.com/docs/en/permissions)、[Codex config basics](https://learn.chatgpt.com/docs/config-file/config-basic)、[Codex sandbox and approvals](https://learn.chatgpt.com/docs/agent-approvals-security)。利用時に[方法の見直し](freshness.md)へ。

公式配置版の実効確認と環境制約は [秘密と実効権限](../safety.md)。Claude sandboxの有無を明示し、本人が有効化した隔離を対応外で黙って解除しない。静的検査は共通設定だけを対象とし、local・user・管理者設定の合成結果を保証しない。既存案件への一斉書換えは行わない。

CodexのTOMLで `model` などトップレベルの項目を追加するときは、最初の `[table]` より前に置く。末尾へ足すと最後のテーブルの一部になり、意図しない設定や安全設定の競合になる。標準部分の中へ混ぜず、更新の差分で配置も確認する。

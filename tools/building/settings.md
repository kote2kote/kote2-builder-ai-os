# AI別の設定と権限

AIの入口・設定を追加/変更する時に読む。共通手順 `agent-settings@1`。2026-10-29に公式資料を確認した雛形で、全環境での実効設定の検証済み印ではない。

## Claude Code

- 案件の `CLAUDE.md` は共通 `AGENTS.md` を参照する薄い入口。設定候補の実物は [claude-settings.json](templates/claude-settings.json) → 案件 `.claude/settings.json`。ローカル設定や管理者設定の内容を秘密ごと収集しない。対象案件で読み込まれた設定と警告を確認する。
- 秘密の読み取り禁止、公開/破壊の確認要求を保持する。`.env.example`など値のない雛形を必要以上に止めない。追加の認証ファイルは秘密の本文を読まずファイル種別を確認して禁止候補へ加える。
- hooksやallow、MCP、サンドボックス解除を標準で足さない。必要なら目的・実行コード・通信先・発火条件・対応OS・失敗時の動作を別途検証して了承を得る。Bashの雛形は取得した公式例の `Bash(git push *)` 形式を使い、旧版の `:*` が全環境で同じように効くとは仮定しない。

## Codex

- 共通入口は `AGENTS.md`。設定候補の実物は [codex-config.toml](templates/codex-config.toml) → 案件 `.codex/config.toml`。`on-request`・`workspace-write`・シェル通信無効を出発点とし、モデルや認証は指定しない。グローバル設定・認証ファイルへ書かない。
- project設定は信頼済み案件でのみ読み込まれる。起動時の実効設定・承認方式・書込範囲・通信可否を確認する。CLIやホストの上位設定が優先する場合がある。T3などのホストが別の権限を使う時に、雛形が強制すると説明しない。
- Web検索も通信であり、シェル通信無効だけで無通信を保証しない。雛形では検索も無効。必要な公式資料の取得は利用環境の許可に従い、本人へ通信が必要なことを説明する。資料取得のために案件をfull-accessへ変えない。

## 共通の限界

deny規則はシェルや他の道具からの秘密到達を完全遮断するものではない。静的検査は実行時の承認・権限を強制しない。厳密な隔離が必要なら実行環境/OS権限を別途設計する。設定ファイルが存在する、構文が通る、実際に適用された、の3つを分ける。

公式根拠: [Claude settings](https://code.claude.com/docs/en/settings)・[permissions](https://code.claude.com/docs/en/permissions)、[Codex config basics](https://learn.chatgpt.com/docs/config-file/config-basic)、[Codex sandbox and approvals](https://learn.chatgpt.com/docs/agent-approvals-security)。利用時に[方法の見直し](freshness.md)へ。

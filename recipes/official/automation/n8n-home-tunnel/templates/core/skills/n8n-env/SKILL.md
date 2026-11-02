---
name: n8n-env
description: ユーザーが「n8n 起動して」「n8n 止めて」「n8n の状態見せて」「つながらない」「ワークフローを作って / 直して / 試して」「ワークフローを書き出して / 読み込んで」「n8n のバージョンを上げて」「片付けて」と言った時に、このマシン専用の n8n(Docker)と専用トンネルを scripts/・MCP・wf.mjs で操作・点検する。
---

# SKILL: n8n-env — このマシン専用 n8n の起動・点検・ワークフロー出し入れ

## トリガー

- 「n8n 起動して」「公開して」 → 起動
- 「止めて」 → 停止
- 「状態見せて」「つながらない」「落ちてる?」 → 点検
- 「ワークフローを作って / 直して / 試して」 → MCP で直接操作
- 「このワークフローを講座用に書き出して」「この JSON を読み込んで」 → ワークフローの出し入れ
- 「n8n のバージョンを上げて」 → 更新
- 「片付けて」「もう使わない」 → 片付け(確認ゲートあり)

## 前提(毎回守る)

- マシンごとの値(公開 URL / トンネル名 / MCP 名 / コンテナ名 / ボリューム名 / ポート / 版)は **すべて `.env`** にある。スクリプトもこの SKILL も値を直書きしない
- 触ってよいのは **この `.env` が指すトンネル・コンテナ・ボリュームだけ**。同じマシンや同じ Cloudflare アカウントにある他の n8n・他のトンネルには触らない
- cloudflared は必ず `--config` でプロジェクト内の設定を明示する(明示しないと `~/.cloudflared/config.yml` の既存トンネルを読んでしまう)
- `.env` は Read しない(deny 設定済み)。値が必要な処理はスクリプトに読ませ、画面に出さない
- API キーはユーザー本人が `.env` に貼る。チャットで受け取らない

## 手順

### 起動(初回はセットアップから)

1. `.env` と `cloudflared/config.yml` が無ければ `bash scripts/setup.sh`(トンネル作成・DNS 登録・`.mcp.json` 作成。上書きはしない)
2. `bash scripts/up.sh`
3. 「まだ公開していません」と出たら、オーナー未作成。ユーザーに「このマシンのブラウザで `http://127.0.0.1:{N8N_LOCAL_PORT}` を開いてオーナーを作ってください」と案内し、作成後にもう一度 `up.sh`
   - オーナー未作成のまま公開しない理由: 最初に URL を開いた人がオーナーになれてしまう

### 停止 / 点検

- 停止: `bash scripts/down.sh`(データは残る)
- 点検: `bash scripts/status.sh` の NG 行から原因を切り分ける
  - コンテナ NG → `docker compose logs --tail 50 n8n`
  - トンネル NG → `cloudflared/run/cloudflared.log` の末尾
  - 手元 OK・公開 NG → トンネル停止か DNS。`status.sh` を 30 秒後に再実行してから判断

### MCP で直接いじる(作る・直す・試す。メインの経路)

n8n 内蔵の MCP サーバー(n8n 2.13 以降で作成・編集に対応)を Claude Code の道具として使う。

1. 初回だけ(ユーザーの操作): n8n の **Settings → Instance-level MCP → Enable MCP access**。「Expose all workflows」を選ぶと、既存・新規のワークフローがすべて対象になる(個別に外せる)
2. `.mcp.json`(`setup.sh` が `.env` の `MCP_NAME` と `N8N_HOST` から作る)がプロジェクトに登録済み。Claude Code を開き直して許可 → `/mcp` で `MCP_NAME` を選び **Authenticate**(ブラウザで n8n にログインして許可)
3. 以降は MCP の道具で検索・詳細取得・作成・編集・テスト実行・公開 / 停止ができる
   - 作ったら必ずテスト実行して結果を確かめてから公開(有効化)する
   - 「Available in MCP」がオフのワークフローは検索に概要しか出ない。触れない時はそこを疑う
- 切り分け: `https://{N8N_HOST}/mcp-server/http` に POST して **404 = MCP 未有効 / 401 = 有効(認証待ち)**
- claude.ai にも同じ URL のコネクタを足してよい。URL が完全に同じなら Claude Code ではプロジェクト登録が優先され、コネクタは隠れる(二重にならない)

### ワークフローの出し入れ(REST API。配布用・無人処理用)

`.env` に `N8N_API_KEY` が必要(n8n の Settings > n8n API で発行)。

```bash
node --env-file=.env .claude/skills/n8n-env/wf.mjs list
node --env-file=.env .claude/skills/n8n-env/wf.mjs export <workflowId>   # → workflows/<名前>.json
node --env-file=.env .claude/skills/n8n-env/wf.mjs import workflows/<file>.json
```

- 書き出しは ID・有効状態・共有情報を外した配布用の形になる。認証情報の中身は入らない(名前だけ表示される)
- 読み込みは停止状態で作られる。認証情報を設定してから有効化する
- ノードの typeVersion やパラメータ構造は推測しない。同種ノードを使う既存ワークフローを読んでから真似する(`knowledge/n8n.md` の定石)

### バージョンを上げる(確認ゲート)

1. 先に「リビジョン保存しますね」と伝えて保存し、使っているワークフローを `export` しておく
2. `.env` の `N8N_VERSION` を書き換えるのはユーザー(`.env` は AI が読まない)。新しい版は https://github.com/n8n-io/n8n/releases で確認する
3. `bash scripts/up.sh` → `status.sh` で緑を確認

### 片付け(確認ゲート)

`bash scripts/teardown.sh` は対話式(トンネル名の入力 → データ削除の yes/No)。AI が勝手に実行しない。ユーザーに黒い画面で実行してもらう。最後に案内される DNS レコードの削除は Cloudflare ダッシュボードで手作業。

## ハマりどころ(踏んだら追記する)

<!-- 開発中にハマって解決した事象をここに追記する。型は下記 -->
<!--
### {現象を一行で}(YYYY-MM 検証)

- 現象: 何が起きたか
- 原因: なぜ起きたか
- 対処: どう直したか(なぜ効くか)
-->

### cloudflared に `--config /dev/null` を渡すと管理コマンドが「設定が空」エラーを出す(2026-09 検証)

- 現象: `cloudflared tunnel --config /dev/null list` が `Configuration file /dev/null was empty` をエラーで出す(結果は返るが紛らわしい)
- 原因: cloudflared は空の設定ファイルをエラー扱いにする。既存の `~/.cloudflared/config.yml` を避けたいだけなのに逆効果
- 対処: 中身が 1 行だけのダミー `cloudflared/admin.yml`(`no-autoupdate: true`)を `--config` に渡す。既存設定も読まず、エラーも出ない

### healthz が 200 になった直後は `/rest/settings` がまだ応答しない(2026-09 検証)

- 現象: 起動直後のオーナー作成判定が「確認できません」になり、`up.sh` が中止する
- 原因: n8n は healthz を先に返し、REST API の準備が数秒遅れる
- 対処: 判定を 2 秒おきに最大 30 秒リトライする(`up.sh`)。判定できないうちは公開しない側に倒す

### MCP の URL が 404 を返す(2026-09 検証)

- 現象: `https://{N8N_HOST}/mcp-server/http` が 404
- 原因: n8n の設定で MCP をまだ有効にしていない(有効化すると認証待ちの 401 に変わる)
- 対処: Settings → Instance-level MCP → Enable MCP access

## 学びの追記ルール

上の「ハマりどころ」セクションに **3〜5 行で追記** する:
- 何が起きたか(現象)
- なぜ起きたか(原因)
- どう直したか(対処、なぜそれが効くか)

self-heal.md の流れと連動。

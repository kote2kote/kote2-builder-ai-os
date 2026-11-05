# スキルの共通正本とAI別の入口

レシピや案件にスキルを足す時に読む。共通手順 `skill-sharing@1`。

Wikiに蓄積した経験から候補を探し、レシピとスキルを作るときは [経験の再利用](../experience.md)。レシピの知識・判断と、スキルの起動条件・進め方を分ける。下書きは `recipes/<id>/skill/<skill-id>/`、了承後の導入先は下記。導入先へ勝手に作らない。スキル内の同梱知識は元レシピID@版と照合し、単独で持ち出せる一式にする。

Codexのrepo用正本は `.agents/skills/<id>/SKILL.md`。Claudeでも使う場合は同じスキル一式を `.claude/skills/<id>/` に配置し、共通部分をbytesで照合する。相対参照するscripts/references/assetsも一緒に扱い、本文だけ一致で合格にしない。リンクの追跡や親ディレクトリ外の参照を同期とみなさない。

OSには最初から4つのスキルが `tools/skills/<id>/` に入っている（図解 `visualize-project-architecture`・説明動画 `explainer-video`（Claude Code専用）・作る前の試作 `create-prototype`・見た目の確認 `design-review`）。OS更新で届く場所に置くため、両AIの自動の探索先ではなく `AGENTS.md` の入口から読む。案件を直接開いて本物のスキルとして使いたいと頼まれた時だけ、上の決まりで案件へ写す（説明動画はClaude側だけ）。ワークスペースの `.agents/`・`.claude/skills/` へは自動で写さない。`tools/skills/` はOSのファイルなので、本人の学び・直しは Wiki か案件の写しに置く。

必要なスキルだけ配置する。`SKILL.md`の`name`・`description`は必須で、用途と使う時を短く説明する。実装手順の全文を常時入口に貼らない。説明が必要な時だけ読み込む。`.codex/skills/`をrepoの共通探索先と決めつけない。

静的検査では `build-contract.json` の `skills` に**共通スキルだけ**列挙する。両AI指定時は各一式を照合する。Claude専用のagentsやモデル指定などは共通化せず、READMEへ専用/未対応と書き、相手側で実行可能と案内しない。共通スキルがないなら空配列でよい。名前だけの空スキルを作らない。

実AIで発見・本文読込・必要な参照先の解決を確認してから読込済みと記録する。片側の成功や静的同期だけで両対応にしない。設定は [AI設定](settings.md)、完了判定は [検証](verification.md)。

公式根拠（2026-10-29取得）: [Codex Build skills](https://learn.chatgpt.com/docs/build-skills)、[Claude skills](https://code.claude.com/docs/en/skills)。仕様の変更は[方法の見直し](freshness.md)で扱う。

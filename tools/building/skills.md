# スキルの共通正本とAI別の入口

## Wikiで一覧・呼び出し方を見る

Wikiの上部の「スキル」で、名前・説明・対応AI・置き場と、**呼び出しコマンド＋自然な呼びかけ言葉**をセットで見られる。どちらもコピーできるが実行はしない。Codexの `$design-review` と「この画面のデザインをレビューして」、Claude Codeの `/design-review` と同じ依頼文のように、対応するAIの入力欄で使う。端末コマンドではない。Claudeの `user-invocable: false` は手動呼出不可、`disable-model-invocation: true` は明示指定が必要。表示は配置の発見であり、そのセッションで実際に有効なことの保証ではない。

作業場直下の `.agents/skills/`・`.claude/skills/`、個人用の同じ配置とCodex設定先の `skills/` の直下を読み、開く・再読込・タブ復帰で更新する。隠しフォルダ・リンク・案件内・祖先・プラグイン内部は探索対象外。非対応の形式・読取不可・上限による未取得を表示する。常駐監視・自動導入・外部送信はしない。追加後のAI側の再読込が必要なら、使うAIの手順を確認する。

自分のスキルは必須の `name` と `description` に加え、任意で次の1行をメタデータへ追加すると、Wikiの呼びかけ例を指定できる。指定がなくても汎用の依頼文が出る。OS管理対象の原本は直接変更せず、自分の追加スキルで使う。

```yaml
metadata:
  wiki-prompt: "この月報を、読みやすい文章に整えて"
```

OS全体の入口は [OS機能一覧](../features.md)。機能案内は個人Wikiの記録・グラフと分けて読み取り専用で表示する。

## 配置と共通化

レシピや案件にスキルを足す時に読む。共通手順 `skill-sharing@1`。

Wikiに蓄積した経験から候補を探し、レシピとスキルを作るときは [経験の再利用](../experience.md)。レシピの知識・判断と、スキルの起動条件・進め方を分ける。下書きは `recipes/<id>/skill/<skill-id>/`、了承後の導入先は下記。導入先へ勝手に作らない。スキル内の同梱知識は元レシピID@版と照合し、単独で持ち出せる一式にする。

Codexのrepo用正本は `.agents/skills/<id>/SKILL.md`。Claudeでも使う場合は同じスキル一式を `.claude/skills/<id>/` に配置し、共通部分をbytesで照合する。相対参照するscripts/references/assetsも一緒に扱い、本文だけ一致で合格にしない。リンクの追跡や親ディレクトリ外の参照を同期とみなさない。

OS標準の共通3スキル（図解 `visualize-project-architecture`・試作 `create-prototype`・見た目 `design-review`）は `.agents/skills/<id>/` と `.claude/skills/<id>/` の公式探索先へ、説明動画 `explainer-video` は `.claude/skills/` だけへ置く。本文と付属資産を一式で持ち、自然言語で必要時に起動する。案件単独でも使いたい依頼では上の決まりで一式を写す。標準と同名の独自Skillは上書きせず差分を確認する。本人の学びはWikiか案件の写しへ。旧 `tools/skills/` は移行案内であり実行入口ではない。

必要なスキルだけ配置する。`SKILL.md`の`name`・`description`は必須で、用途と使う時を短く説明する。実装手順の全文を常時入口に貼らない。説明が必要な時だけ読み込む。`.codex/skills/`をrepoの共通探索先と決めつけない。

静的検査では `build-contract.json` の `skills` に**共通スキルだけ**列挙する。両AI指定時は各一式を照合する。Claude専用のagentsやモデル指定などは共通化せず、READMEへ専用/未対応と書き、相手側で実行可能と案内しない。共通スキルがないなら空配列でよい。名前だけの空スキルを作らない。

実AIで発見・本文読込・必要な参照先の解決を確認してから読込済みと記録する。片側の成功や静的同期だけで両対応にしない。設定は [AI設定](settings.md)、完了判定は [検証](verification.md)。

公式根拠（2026-10-29取得）: [Codex Build skills](https://learn.chatgpt.com/docs/build-skills)、[Claude skills](https://code.claude.com/docs/en/skills)。仕様の変更は[方法の見直し](freshness.md)で扱う。

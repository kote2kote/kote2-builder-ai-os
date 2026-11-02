---
name: explainer-video
description: キャラクター(同梱のひまわり猫・差し替え可・無しも可)が図の横で解説する、字幕つきの説明映像(HTML で再生 + MP4 書き出し、1920×1080・音なし)を作る。「映像で説明して」「説明映像を作って」「解説動画にして」「このプロジェクトの仕組みを動画にして」「〇〇とは を動画で」と頼まれた時に使う。ビルダー直下では「このスキルを〇〇(output のプロジェクト)にも入れて」「説明映像も入れて」の時に、生成プロジェクトへ写す手順も持つ。静止画 1 枚の図解、宣伝だけの演出映像、根拠を確かめられない話題には使わない。
---

# 説明映像を作る

図(箱と矢印の地図)をカメラで順に寄りながら、キャラクターが字幕で解説する映像を作る。箱には絵(同梱のアイコン 50 個 + 話題に合わせて描き足すイラスト)を添えて、文字だけの図にしない。**場面データ(`scene.js`)を書くだけ**で、再生(ブラウザ)と書き出し(MP4)は同梱のエンジンが受け持つ。演出を毎回ゼロから書かない。

- 解説モード: 「MCP とは」のように、話題と出典から図にする(例: `examples/mcp/`)
- 仕組みモード: このプロジェクト(または指定されたもの)の「誰が何をするとどこで何が起き、何が返るか」を、実ファイルを根拠に図にする

**Claude Code 専用・モデルは Opus 5.5 推奨**(`/model` で選ぶ)。Codex での映像づくりは確かめていない。Codex から頼まれた時は、Claude Code で頼むよう 1 回伝える。

## 成果物

作業フォルダ(このスキルがあるプロジェクトのルート。ビルダー直下ならビルダー直下)の `explainer-videos/{名前}/` に作る。`{名前}` は英小文字とハイフン。

- `evidence.md` — 映像に載せた事実と出典、矢印ごとの起点・終点・動くもの
- `plan.md` — 読者、見終わった後の一文、場面表
- `scene.js` — 場面データ(正本。直す時はここだけ)
- `index.html` — 読み込みだけの入れ物(ダブルクリックで再生)
- `{名前}.mp4` — 共有用の書き出し(ffmpeg がある時)

## 手順

### 1. 根拠を集める(`evidence.md`)

1. 読者を決める。指定が無ければ「初めて聞く非エンジニア」
2. 解説モード: 公式ドキュメントなど一次情報を読み、映像で言うことごとに「確認した事実(原文の言い回し)/ 出典 URL / 確認日」を表にする。原文に無い言い換えは「**解釈**」と書き分ける。確かめられない話題は作らずに止まって伝える
3. 仕組みモード: `CLAUDE.md`・README・入口の処理・保存先・外部連携を必要な範囲だけ読む。`.env`・鍵・トークン・個人プロフィールは読まない。秘密値・長い実パス・公開不要の識別子は映像に載せない
4. 描く矢印ごとに「ID / 起点 / 終点 / 動くもの」を表にする。目的の違う流れ(公開・保存・削除など)を 1 本の物語に混ぜない
5. 省いたことを最後に書く(初めての人に要らない細部)

### 2. 設計する(`plan.md`)

- 読者と「見終わった後の一文」
- 地図の区画(例: 左「これまで」/ 右「これがあると」)と、最後に全体へ引いた時に 1 枚で残るもの
- 場面表: 場面 / 秒 / ポーズ / 中身。**全体 30〜90 秒、1 場面 4〜8 秒、字幕は 1 場面 1 文で 40 字前後まで**
- 色の意味を決める: `g` = 主な流れ / `o` = 返事・注意 / `s` = 参照・比較(凡例に書く)
- **絵を決める**: 箱ごとに絵を 1 つ選び、場面表に「絵」の列を足す。選ぶ元は同梱の一覧(下の「絵の一覧を見る」)。同じものには映像の最後まで同じ絵を使う。一覧に無い物だけ `art` で描き足す(同梱で言える物は描かない)。目安は 1 本で 1〜6 個(同じ形の色違いは 1 個と数える)。仕組みの話なら 1〜2 個で足りるが、歴史・文化・趣味など同梱から遠い話題では、人物や建物を描いてよい
- 人物や建物を描く時は説明用の**イメージ**にとどめる: 実在の人物・作品のキャラクター・公式絵に似せない。絵だけの部品なら見出しに「(イメージ)」と書き、`evidence.md` に「絵はイメージ」と 1 行残す

### 3. 場面データを書く(`scene.js`)

- `examples/mcp/` の `index.html` と `scene.js` を写して始める。`index.html` の読み込み先は、`explainer-videos/{名前}/` から見て `../../.claude/skills/explainer-video/...` に直す(下の雛形)
- 書き方の正本は `references/scene-format.md`。要点: 座標は 1920×920 の地図の上の px / 時刻はすべて「場面の頭からの秒」/ `dur` を変えると後ろが自動でずれる
- 文字は地図の上で 22px 以上(カメラで寄ると大きく見えるが、全体に引いた場面でも読めること)
- 絵の付け方(正本は `references/scene-format.md`「絵」): 箱に `icon: '名前'`(左に台紙つきで添える。狭い箱は `iconAt: 'top'`)/ 絵だけの部品 `cls: 'art'` / 文中に `<i data-icon="名前"></i>` / 動くラベルに `packetIcon` / 札に `icon`。字幕が話している部品は `at` の `pulse` で一瞬跳ねさせる。絵を添えると文字の幅が減るので、箱の `w` を広げる
- 描き足す絵(`art`)は同梱と同じ絵柄にする: 塗りは色のクラス(`f-frame` 緑 / `f-leaf` 薄緑 / `f-accent` 錆色 / `f-wood` 段ボール色 / `f-sun` 黄 / `f-sky` 灰青 / `f-paper` クリーム / `f-card` 白 / `f-ink` 濃い色)、輪郭は `ol`、線だけは `ln`。部品は 3〜12 個の平らな形。**色を直接書かない**(`theme` で色を変えても追従しなくなる)。グラデーション・影・光の粒・絵の中の文字は描かない
- 会社や製品のロゴ(Notion・GitHub など)は描かない。中身を表す一般の絵(文書・プログラム・フォルダ)で代える

```html
<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{題名}</title>
<link rel="stylesheet" href="../../.claude/skills/explainer-video/engine/explainer.css">
</head><body>
<script src="../../.claude/skills/explainer-video/character/character.js"></script>
<script src="../../.claude/skills/explainer-video/engine/icons.js"></script>
<script src="scene.js"></script>
<script src="../../.claude/skills/explainer-video/engine/explainer.js"></script>
</body></html>
```

### 4. 静止画で確かめる

```bash
node .claude/skills/explainer-video/engine/render-video.mjs explainer-videos/{名前}/index.html --stills 2,10,20,{最後の 1 秒前} --stills-dir {一時フォルダ}
```

- 場面データに無い id・ポーズ・絵の名前・長さ超えがあると、エラー文を出して止まる(黙って書き出さない)。文の場面番号を見て直す
- 「注意: はみ出し: 箱「…」」が出たら、その箱の `w` / `h` を広げるか言葉を短くする(書き出しは止まらないが、そのままにしない)
- 撮った静止画を**画像として開いて**見る。確認すること:
  - 文字切れ・重なり・画面外へのはみ出しが無い(箱の中の文字は折り返さない設定なので、長いと箱からはみ出す)
  - 各場面で、カメラの中心に字幕が話している部品が入っている
  - 矢印の向きと動くラベルが `evidence.md` の表と一致する
  - キャラと字幕が図の大事な部分を隠していない(隠れるなら `side: 'R'` で左右を入れ替えるか、カメラをずらす)
  - 絵が箱の中身と合っていて、同じものに同じ絵を使っている。描き足した絵(`art`)が同梱の絵と並べて浮いていない
- 直すのは `scene.js` だけ。最大 2 回まで見直して直す

**絵の一覧を見る**(どの名前が使えるか迷った時):

```bash
node .claude/skills/explainer-video/engine/render-video.mjs .claude/skills/explainer-video/references/icon-catalog/index.html --stills 1 --stills-dir {一時フォルダ}
```

撮った画像に、名前と意味つきで全部の絵が並ぶ。名前と意味の文字だけなら `engine/icons.js` を読めばよい。

### 5. 書き出す

```bash
node .claude/skills/explainer-video/engine/render-video.mjs explainer-videos/{名前}/index.html explainer-videos/{名前}/{名前}.mp4
```

- 必要なもの: Node.js 18 以上 / Chrome か Edge(自動で探す。見つからない時は `--browser "{実行ファイルのパス}"`)/ ffmpeg(MP4 の時だけ)
- ffmpeg が無い時は、エラー文の案内(Mac: `brew install ffmpeg` / Windows: `winget install Gyan.FFmpeg`)を見せて、**入れてよいか聞いてから**入れる。入れない場合も `index.html` をブラウザで開けば再生できる(クリックで一時停止、R で最初から)
- Windows で入れた直後は、同じ端末からは ffmpeg が見つからない。端末を開き直してもらうか、開き直せない時は `FFMPEG_PATH="{ffmpeg.exe のパス}"` を付けて実行する(winget の置き場は `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_...\...\bin\ffmpeg.exe`)
- 1 分の映像で 2〜4 分かかる(Windows や数年前の PC では倍くらい。実測: Core i5-7500 で 70 秒の映像に約 7.5 分)。一部だけ撮り直す時は `--from 秒 --to 秒`

### 6. 報告する

MP4(無ければ `index.html`)、`evidence.md` の順に案内する。「この映像で分かること」を 1 文、未確認・解釈で言っていることがあれば 1〜3 点に絞って書く。

## キャラクター

- 同梱は「ひまわり猫」の 8 ポーズ: `angry`(困る)/ `crossed`(注意)/ `surprised`(登場)/ `thinking`(問い)/ `cheer`(できた。跳ねる)/ `bow`(まとめ)/ `point`(ここを見て)/ `smile`(案内)
- **差し替える**: 同じ縮尺で切り抜いた透過 PNG を `character/` に置き、`character/character.js` の `poses` 表(ポーズ名 → ファイル名)を書き換える。場面データはポーズ名で書くので、名前を揃えれば `scene.js` は直さなくてよい
- **キャラ無し**: その映像の `index.html` から `character.js` の行を消す。字幕が左に広がり、タイトルは左寄せになる。`pose` は無視される
- ひまわり猫の画像の利用条件は `character/TERMS.md`(このビルダーで作る映像に使える。画像だけを取り出しての再配布・販売はしない)

## 生成プロジェクトに入れる(ビルダー直下で使う時だけ)

「このスキルを〇〇にも入れて」「説明映像も入れて」(新しく作るプロジェクトの時も、作ったあとの時も)と頼まれた時だけ行う。頼まれていないプロジェクトには入れない・勧めない。

1. 写す先を一覧で見せて承認を取る: `output/{name}/.claude/skills/explainer-video/`(このフォルダ一式。`SKILL.md` / `engine/` / `character/` / `references/` / `examples/`)と、`output/{name}/CLAUDE.md` の「できること」に足す 1 行(「〇〇を映像で説明して → 説明映像(explainer-video。Claude Code 専用・Opus 5.5 推奨)」)
2. 写し先に `explainer-video/` が既にあれば上書きせず止め、差分を見せる(更新は下の「骨格の更新」)
3. フォルダごとバイトそのままコピーする。`CLAUDE.md` は 1 行の追記だけ
4. プロジェクトに `dashboard.html` があれば「できること」にも同じ 1 行を反映する(スキルを足した時の約束。`builder.md`「スキル同期の契約」)。Codex 両対応のプロジェクト(`.codex/config.toml` がある)では、同じ変更内で `.agents/skills/explainer-video/SKILL.md` の薄いアダプター(`templates/codex/README.md`「スキル同期」の形。description はこのファイルと一字一句同じ)と `AGENTS.md` の対応表を足し、`bash scripts/check-sync.sh` で 0 FAIL を確かめる(アダプターはスキル同期の契約のため。映像づくりは Claude Code 専用のまま)
5. 写した先で `node .claude/skills/explainer-video/engine/render-video.mjs .claude/skills/explainer-video/examples/mcp/index.html --stills 25 --stills-dir {一時フォルダ}` が通ることを確かめて報告する

**骨格の更新**(「説明映像の骨格を最新にして」): `engine/` / `character/character.js` 以外の `character/` 画像 / `references/` / `examples/` / `SKILL.md` を写し直す(差分を見せて承認後)。**触らない**: `explainer-videos/`(作った映像)と、差し替え済みの `character/character.js`・キャラ画像(同梱と違うファイルは残す)。

## ハマりどころ

### キャラ画像の切り抜きで瞳が透ける(2026-10 検証)

- 現象: 明るい背景に置くと、キャラの瞳が白っぽく抜けて見える。首まわりにも白い点が出る
- 原因: 画像の端の黒い帯を消すために「ほぼ真っ黒な点をすべて透明にする」処理をすると、瞳の黒まで消える
- 対処: 黒い点は「画像の外枠につながっているかたまり」だけ消す。体の内側の点は元の透明度のまま残す(キャラを差し替える時の切り抜きで同じ罠を踏む)

### 絵が台紙からずれて、箱の文字に重なる(2026-10 検証)

- 現象: 箱に添えた絵が、台紙(淡い四角)の外へ大きくはみ出して文字に重なる
- 原因: 矢印を描く SVG 用の CSS を `#map svg` と書くと、地図の中にある絵の SVG 全部にも効いて、絵が箱の左上を基準に置き直される
- 対処: 矢印用の指定は `#map > svg`(地図の直下だけ)に絞る(`explainer.css` に反映済み)。CSS を書き換える時は、指定が絵の SVG(`.art-svg`)にも当たらないか確かめる

### 上下中央そろえの箱で、上へのはみ出しを見逃す(2026-10 検証)

- 現象: 絵を上に添えた箱で、台紙が箱の上の線に食い込んでいるのに「注意: はみ出し」が出なかった
- 原因: 箱は中身を上下の真ん中にそろえるので、入りきらない分が上下に半分ずつ出る。ブラウザの scrollHeight は下へのはみ出ししか数えない。測り直すと今度は改行(`<br>`)が高さ 0 で箱の左上にいる扱いになり、問題の無い箱まで引っかかった
- 対処: 箱の中の要素の上端・下端を測り、箱の線から 4px 以内に迫ったら「注意」にする(高さ 0 の要素は測らない。`explainer.js` に反映済み)

### 書き出しが「done」の後に終わらず、次の書き出しが始まらない(2026-10 検証)

- 現象: `done:` が表示されたのにコマンドが終わらない(毎回ではなく時々)
- 原因: 終了時に Chrome へ `Browser.close` を送り、その返事を待っていた。Chrome が返事をせずに閉じると永久に待つ
- 対処: 返事・Chrome の終了・3 秒のどれか早い方で先へ進み、最後に `process.exit` で必ず終わる(`render-video.mjs` に反映済み)

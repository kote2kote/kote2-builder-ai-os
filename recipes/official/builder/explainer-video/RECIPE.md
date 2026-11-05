<!-- ============================================================ -->
<!-- recipe: explainer-video(説明映像 = キャラが図の横で解説する動画)              -->
<!-- 由来: chat-desk の lab で 2026-09-26 に仕組み映像・プロモを試作 → 2026-10-08 に  -->
<!--       場面データ + 共通エンジンへ切り出し(解説モード「MCP とは」53 秒で実証)。   -->
<!--       kote2 決定(2026-10-08): 猫同梱・差し替え可 / Free+Pro / 生成物にも opt-in / 音なし -->
<!--       kote2 決定(2026-10-09): 生成プロジェクトへは頼まれた時だけ / ビルダー直下でも作れる -->
<!--       2026-10-12(1.1.0): 文字だけの図にしない = 絵(同梱アイコン 50 個 + 映像ごとの描き足し) -->
<!-- 状態: スキル一式の正本は templates/core/explainer-video/(このパッケージ)。          -->
<!-- ★固有値を焼かない: ドメイン / 実パス / 氏名 / メール / API キーは本文に書かない。 -->
<!-- v2: 先頭メタは recipe.json。templates/core にスキル一式。スクショは assets/screens に 3 枚。 -->
<!-- ============================================================ -->

# explainer-video — 説明映像(キャラが図の横で解説する動画)

> **このレシピは導入しません（2026-11-05、過去の記録）。** 説明動画は OS の初期スキル `tools/skills/explainer-video/`（Claude Code 専用）として最初から入っています。頼まれたらそちらを使ってください。以下は旧ビルダーでの設計と確認の記録です。本文中の `templates/core/explainer-video/`・`.claude/skills/explainer-video/`・`output/` などは旧ビルダーの置き場で、このパッケージにはスキル一式を同梱していません。

箱と矢印の「地図」をカメラで順に寄りながら、キャラクター(同梱のひまわり猫・差し替え可・無しも可)が字幕で解説する 1920×1080 の映像を作る**スキル 1 つ**を、**ビルダー直下**の `.claude/skills/explainer-video/` に足す拡張レシピ(`target: builder`)。AI は場面データ(`scene.js`)を書くだけで、再生(ブラウザ)と MP4 書き出しは同梱のエンジンが受け持つ。生成プロジェクトには**頼まれた時だけ**写す(Codex の図解スキル `visualize-project-architecture` と同じ立ち位置の「動く版」)。

- **対応 AI**: **Claude Code 専用・モデルは Opus 5.5 推奨**(kote2 決定 2026-10-09)。Codex での映像づくりは未検証(§9)
- **この設計書の肝**: 演出を毎回ゼロから書かない。映像の差は**データ**(地図・絵・場面・字幕・秒)だけに閉じ込め、根拠表(`evidence.md`)と静止画の目視で「事実と絵のずれ」を潰してから書き出す。箱には絵を添えて文字だけの図にしない(同梱のアイコン + 話題に固有の物だけ描き足す。1.1.0〜)。

---

## 1. これは何 / 機能構成 + 完成形(受け入れ基準)

### 機能構成(★ここだけが必須/任意/不採用を決める正本。他章はこの表を参照する)

| ID | 機能 | 状態 | Phase | 完成判定 |
|---|---|---|---|---|
| CORE-01 | スキル本体: `SKILL.md`(発火条件・手順 = 根拠 → 設計 → 場面データ → 静止画確認 → 書き出し → 報告)+ `references/scene-format.md`(場面データの書き方)+ `examples/mcp/`(解説モードの完成例) | required | Phase 1 | PASS 必須 |
| CORE-02 | エンジン: `engine/explainer.js`(場面データ → `render(t)` で t 秒目の 1 コマを決定論で描く。書き間違い = 無い id / ポーズ / 長さ超えを console.error)+ `explainer.css`(kote2 標準テーマ。`theme` で上書き) | required | Phase 1 / 2 | PASS 必須 |
| CORE-03 | 撮影: `engine/render-video.mjs`(追加パッケージ不要。手元の Chrome / Edge を DevTools のパイプで操作。`--stills` で確認用の静止画、既定で ffmpeg に流して MP4。ページのエラーがあれば失敗で止まる) | required | Phase 2 | PASS 必須(MP4 だけは ffmpeg がある時) |
| CORE-04 | キャラクター: `character/`(ひまわり猫 8 ポーズ + `character.js` の表 + `TERMS.md` の利用条件)。差し替え = 画像と表だけ / キャラ無し = `index.html` から 1 行外す | required | Phase 1 / 2 | PASS 必須 |
| CORE-05 | 絵: `engine/icons.js`(同梱アイコン 50 個。塗りは色クラスで `theme` に追従)+ `scene.js` の `art`(その映像だけの描き足し)+ `references/icon-catalog/`(一覧を静止画で見る)。箱の `icon` / 絵だけの `cls: 'art'` / 文中の `<i data-icon>` / 動くラベルの `packetIcon` / 札の `icon`、場面の `pulse`(跳ねる)。箱のはみ出しは「注意」で知らせる | required | Phase 1 / 2 | PASS 必須(1.1.0〜) |
| FEAT-01 | 生成プロジェクトへ写す: 「〇〇にも入れて」「説明映像も入れて」の時だけ `output/{name}/.claude/skills/explainer-video/` へ一式 + CLAUDE.md「できること」1 行(Codex 両対応なら薄いアダプター + AGENTS.md + check-sync) | optional-enabled | Phase 3 | 頼まれたプロジェクトがあれば PASS 必須(無ければ SKIP) |
| FEAT-02 | 音(ナレーション・BGM) | optional-disabled | — | 初版は音なし(kote2 決定)。`dur` を音の長さに合わせられる作りだけ先に入れてある |
| EXCL-01 | 自由演出の映像(プロモ・OP 風。2026-09-26 の試作) | excluded | — | 部品化しない(場面データに乗らない演出は毎回の手作り) |
| EXCL-02 | 生成時に「映像を入れますか」と聞く / 全プロジェクトへ自動で入れる | excluded | — | opt-in は「頼まれた時だけ」(2026-10-09 kote2 決定) |

### 完成形(受け入れ基準)

- [ ] required(CORE-01〜05)がすべて緑(§10 の TEST-001〜004・TEST-008 PASS、ffmpeg がある環境では TEST-005 も PASS)
- [ ] ビルダー直下で「〇〇とは を動画で」が通り、`explainer-videos/{名前}/` に根拠表・設計・場面データ・MP4 がそろう(TEST-007)
- [ ] 頼まれたプロジェクトがあれば FEAT-01 が緑(TEST-006)← ここまでが「完成」

---

## 2. スタック

| 層 | 採用 | 備考 |
|---|---|---|
| AI | Claude Code(Opus 5.5 推奨) | Claude Code 専用。根拠表・場面設計・静止画の見直しを AI が受け持つ |
| 映像の正本 | 場面データ `scene.js`(`window.VIDEO = {...}`) | 1 映像 = 1 ファイル。地図(箱・矢印・札)と場面(秒・ポーズ・字幕・カメラ・出来事)を持つ |
| 描画 | 依存なしの HTML + CSS + SVG(`engine/`) | ネット不要・file:// でそのまま再生。フォントは OS の日本語ゴシック。絵はインライン SVG(`engine/icons.js` と `scene.js` の `art`) |
| 撮影 | Node.js 18+ の標準ライブラリだけ(`render-video.mjs`) | Puppeteer / Playwright を入れない。Chrome / Edge を `--remote-debugging-pipe` で 1 回だけ起動し 1 コマずつ撮る |
| 書き出し | ffmpeg(H.264 / yuv420p / crf 18 / faststart) | MP4 の時だけ必要。無ければ HTML 再生で代わりになる |
| キャラ | 透過 PNG 8 枚 + 表(`character.js`) | 同じ縮尺で切り抜く。合計約 1.9MB |

---

## 3. 魔法のタネ ★変えるな(崩すと別物になる本質)

1. **`render(t)` は決定論**(同じ t なら同じ絵)。再生は毎フレーム呼ぶだけ、書き出しは 1 コマずつ呼んで撮る。時刻をタイマーやアニメーション API に任せると、書き出しでコマ落ち・ずれが出る
2. **時刻はすべて「場面の頭からの秒」**。`dur` を変えれば後ろが自動でずれる。音を足す日はナレーションの長さを `dur` に入れるだけ(FEAT-02 の受け皿)
3. **根拠表 → 設計 → 場面データ → 静止画の目視 → 書き出し**の順。矢印ごとに起点・終点・動くものを表で決めてから描く。確かめられない話題は作らない
4. **書き間違いは止める**。無い id・ポーズ・場面の長さ超えはエラーにして書き出さない(黙って部品が出ない映像を配らない)
5. **キャラは解説役で、実体の代わりにしない**。図の箱・矢印が事実を運び、キャラはポーズで場面の調子を足すだけ(差し替え・無しでも映像の意味は変わらない)
6. **一式はスキルのフォルダに閉じ込める**。ビルダー / プロジェクトの CLAUDE.md・builder.md には発火のための 1 行しか置かない
7. **絵は色を直接書かず、色クラスで塗る**(`f-*` / `ol` / `ln`)。だから `theme` 1 か所で同梱の絵も描き足した絵も一緒に色が変わり、描き足しが同梱と並んで浮かない。描き足しは話題に固有の物だけ(TEST-008 が同梱の絵の色の直書きを止める)

---

## 4. 改変の余地 ★変えていい(knob 3 分類)

- **軽量設定**: 色(`scene.js` の `theme`。`explainer.css` 先頭の CSS 変数。絵の色 `--leaf` `--wood` `--sky` `--paper` `--line` も)/ コマ数(`fps`)/ 地図の大きさ(`map`)/ キャラの大きさ(`character.js` の `scale` / `titleScale`)/ 跳ねるポーズ(`bounce`)
- **機能モジュール**: キャラの差し替え(画像 + `poses` 表)/ キャラ無し(`index.html` から 1 行外す)/ 絵の描き足し(`scene.js` の `art`)/ 同梱の絵を増やす(`engine/icons.js` に 1 行。TEST-008 が絵柄の約束を確かめる)/ FEAT-01(頼まれたプロジェクトへ写す)/ FEAT-02(音。初版 OFF)
- **派生アーキ**(knob ではない。提案 → ユーザー GO): 縦型(1080×1920)の SNS 用(字幕・キャラの配置を作り直す)/ 自由演出(EXCL-01)/ Remotion 等の動画フレームワークへ載せ替え(依存なしの魔法のタネ 1 が崩れる)

---

## 5. 再現の順路(Phase + 検証)

> **UI をゼロから描かない**: スキル一式は `recipe.json` の `templates.core` を **無加工でコピー**する(`templates/core/explainer-video/` → `.claude/skills/explainer-video/`)。

**Phase 0 — 土台**
- 作る: Node.js 18 以上(`node -v`)/ Chrome か Edge / ffmpeg(MP4 を作る時だけ。無ければ入れてよいか聞く。Mac: `brew install ffmpeg` / Windows: `winget install Gyan.FFmpeg`。入れない場合は HTML 再生だけで進める)
- 検証(緑): `node -v` が v18 以上 / Chrome か Edge がある(Phase 2 の TEST-002 で確かめる)/ `ffmpeg -version`(任意)

**Phase 1 — スキルを写す(CORE-01 / CORE-02 / CORE-04 / CORE-05)**
- 作る: `templates.core` の 22 ファイルを `.claude/skills/explainer-video/` へ**バイトそのままコピー**。写し先に `explainer-video/` が既にあれば上書きせず止める(更新は下の「骨格の更新」)。ビルダーの `CLAUDE.md` / `builder.md` は**編集しない**(スキルは `.claude/skills/` に置けば Claude Code が見つける。`builder.md` の「これ作って」拡張レシピ注記と「説明映像」の 1 段落が配線済み)
- 検証(緑): `bash recipe-tests/explainer-skeleton.sh`(TEST-001)

**Phase 2 — 撮れることを確かめる(CORE-02 / CORE-03 / CORE-04 / CORE-05)**
- 作る: なし(同梱の例で確かめる)
- 検証(緑): `bash recipe-tests/explainer-stills.sh`(TEST-002)/ `bash recipe-tests/explainer-guard.sh`(TEST-003)/ `bash recipe-tests/explainer-nocat.sh`(TEST-004)/ `bash recipe-tests/explainer-mp4.sh`(TEST-005。ffmpeg が無ければ SKIP)/ `bash recipe-tests/explainer-icons.sh`(TEST-008)

**Phase 3 — 初めの 1 本(CORE-01 の運用開始)**
- 作る: ユーザーに作りたい話題を 1 つ聞き(無ければ「このビルダーでできること」を仕組みモードで)、`SKILL.md` の手順どおり `explainer-videos/{名前}/` に 1 本作る
- 検証(緑): 手動 TEST-007

**Phase 4 — 生成プロジェクトへ写す(FEAT-01。頼まれた時だけ)**
- 作る: `SKILL.md`「生成プロジェクトに入れる」の手順(一覧を見せて承認 → 一式コピー → CLAUDE.md に 1 行 → Codex 両対応ならアダプター + AGENTS.md + check-sync)
- 検証(緑): `bash recipe-tests/explainer-project.sh output/{name}`(TEST-006)

**骨格の更新(「説明映像の骨格を最新にして」/ ビルダーのアップデート後)**
- 写し直す: `SKILL.md` / `engine/` / `references/` / `examples/` / `character/TERMS.md` と、同梱と同じ中身のキャラ画像・`character.js`(差分を見せて承認後)
- **触らない**: `explainer-videos/`(作った映像)/ 差し替え済みの `character.js` とキャラ画像
- 検証(緑): TEST-001 / TEST-002 / TEST-008
- 1.0.x から上げる時: 作った映像(`explainer-videos/`)の `index.html` は書き換えない(icons.js の行が無くても撮れる)。その映像に絵を足す時だけ、`scene.js` の行の前に `engine/icons.js` を読む行を足す

---

## 6. 固有の地雷 + 直し方

1. **[PIT-EV-SKILL-001] SKILL.md の 1 行目が frontmatter でないと、スキルが永久に発火しない**
   - 症状: 「映像で説明して」と頼んでもスキルが使われず、AI が毎回ゼロから動画を作ろうとする
   - 原因: Claude Code は先頭の YAML frontmatter(`name` / `description`)でスキルを登録する(`builder.md`「SKILL.md の frontmatter」)
   - 直し方: 一式をバイトそのままコピーする(手で書き直さない)。TEST-001 が 1 行目を確かめる
   - 確認環境: mac(2026-10)/ 回帰: TEST-001
2. **[PIT-EV-GUARD-001] 場面データの id やポーズの書き間違いが、黙って「出ない部品」になる**
   - 症状: 書き出した映像で、ある矢印やキャラだけ出ない。エラーは出ない
   - 原因: エンジンは id で部品を引くので、無い id は何も起きないまま過ぎる
   - 直し方: エンジンが読み込み時に全場面の `at` / `pose` / `dur` と絵の名前(`icon` / `packetIcon` / `<i data-icon>`)を照合して console.error、`render-video.mjs` がそれを拾って**撮る前に**止める(場面番号つきの日本語で出る)
   - 確認環境: mac Chrome(2026-10)/ 回帰: TEST-003
3. **[PIT-EV-CLOSE-001] 書き出しが「done」の後に終わらず、次の書き出しが始まらない**
   - 症状: `done:` が出たのにコマンドが終わらない(時々)
   - 原因: 終了時の `Browser.close` の返事を待っていた。Chrome が返事をせずに閉じると永久に待つ
   - 直し方: 返事・Chrome の終了・3 秒のどれか早い方で先へ進み、最後に `process.exit` で必ず終わる(同梱版に反映済み)
   - 確認環境: mac Chrome(2026-10)/ 回帰: TEST-005(連続実行で固まらない)
4. **[PIT-EV-CAT-001] キャラ画像の切り抜きで瞳が透ける**
   - 症状: 明るい背景に置くと瞳が白っぽく抜ける。首まわりに白い点
   - 原因: 端の黒い帯を消すために「ほぼ黒の点をすべて透明」にすると、瞳の黒も消える
   - 直し方: 黒い点は「外枠につながっているかたまり」だけ消す。体の内側は元の透明度のまま(同梱画像は修正済み。差し替える時の切り抜きで同じ罠を踏む)
   - 確認環境: mac(2026-10)/ 回帰: TEST-002 の静止画を目視
5. **[PIT-EV-FFMPEG-001] ffmpeg が無い環境で書き出しが止まる**
   - 症状: `ffmpeg が見つかりません` で exit 1
   - 原因: MP4 の圧縮は ffmpeg に任せている(Node だけでは作れない)
   - 直し方: 入れてよいか聞いてから入れる(Mac: `brew install ffmpeg` / Windows: `winget install Gyan.FFmpeg`、入れた後は端末を開き直す)。入れない場合は `index.html` をブラウザで開いて再生・画面録画で代える。静止画の確認(`--stills`)は ffmpeg 無しで動く
   - Windows の補足: winget はユーザー PATH に `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_...\...\bin` を足すが、**入れたのと同じ Git Bash には反映されない**(`WinGet\Links` も空のことがある)。開き直せない時は `FFMPEG_PATH=<bin>\ffmpeg.exe` を環境変数に置く。`render-video.mjs` と TEST-005 はどちらも `FFMPEG_PATH` を先に見る
   - 確認環境: mac(2026-10)/ win(2026-10。winget の ffmpeg 9.0.2 + `FFMPEG_PATH`)/ 回帰: TEST-005(無ければ SKIP)
6. **[PIT-EV-ICON-001] 箱に添えた絵が台紙からずれて、箱の文字に重なる**
   - 症状: 絵が淡い台紙の外へ大きくはみ出し、箱の左上あたりで文字に重なる
   - 原因: 矢印を描く SVG 用の CSS を `#map svg` と書くと、地図の中の絵の SVG 全部にも `position:absolute` が効く
   - 直し方: 矢印用の指定は `#map > svg`(地図の直下だけ)に絞る(同梱版に反映済み)。CSS を書き換える時は、絵の SVG(`.art-svg`)にも当たらないか静止画で確かめる
   - 確認環境: mac Chrome(2026-10)/ 回帰: TEST-002 の静止画を目視(screens 01 の checks)
7. **[PIT-EV-FIT-001] 上下中央そろえの箱で、上へのはみ出しを見逃す**
   - 症状: 絵を上に添えた箱で台紙が箱の線に食い込んでいるのに、「注意: はみ出し」が出ない
   - 原因: 箱は中身を上下中央にそろえるので、はみ出しが上下に半分ずつ出る。scrollHeight は下側しか数えない。測り直す時、改行(`<br>`)は高さ 0 で左上にいる扱いになり誤検出する
   - 直し方: 箱の中の要素の上端・下端を測り、線から 4px 以内に迫ったら「注意」(高さ 0 の要素は除く。同梱版に反映済み)
   - 確認環境: mac Chrome(2026-10。薬屋の解説映像で発見)/ 回帰: TEST-008

---

## 7. 固有スキル / 道具

- `.claude/skills/explainer-video/SKILL.md` — 「映像で説明して」「説明映像を作って」「解説動画にして」「このプロジェクトの仕組みを動画にして」で発火。ビルダー直下では「〇〇にも入れて」で生成プロジェクトへ写す手順も持つ
- `engine/render-video.mjs` — `node … <index.html> <out.mp4>`(書き出し)/ `--stills 2,10 --stills-dir 一時フォルダ`(確認用の静止画)/ `--from 秒 --to 秒`(一部だけ)/ `--browser パス`。箱のはみ出しは「注意(書き出しは止めません)」で出る
- `references/icon-catalog/index.html` — 同梱の絵の一覧。`--stills 1` で撮ると名前と意味つきで並ぶ(AI が絵を選ぶ時に見る)

---

## 8. ハーネス宣言

**拡張レシピ(`target: builder`)なのでハーネスは焼かない**(標準一式・必須2問・`validate-output.sh`・`recipe/draft.md` は無し)。

- **ビルダー直下に足すもの**: `.claude/skills/explainer-video/`(22 ファイル)。映像を作ると `explainer-videos/{名前}/` ができる
- **編集しない既存ファイル**: `CLAUDE.md` / `builder.md` / `.claude/settings.json` / `dashboard.html`
- **上書きしないデータ**: `explainer-videos/`(作った映像)/ 差し替え済みのキャラ(再実行・更新でも触らない。骨格の写し直しは §5「骨格の更新」だけ)
- 生成プロジェクトとのつながり: 頼まれたプロジェクトにだけ一式を写す(FEAT-01)。写したプロジェクトは単体で動く(ビルダーが無くても映像を作れる)

---

## 9. 適応指示(環境差・安全側・固有値)

- **対応 AI**: Claude Code 専用・Opus 5.5 推奨(`/model` で選ぶ)。Codex では未検証(ビルダー直下は Codex 用の入口を置かない。Codex 両対応のプロジェクトへ写す時のアダプターはスキル同期の契約のためだけ)。Codex から頼まれたら、Claude Code で頼むよう 1 回伝える
- **安全側デフォルト**: 公開・アップロードはしない(作るのは手元のファイルだけ)。ffmpeg の導入は聞いてから。仕組みモードで `.env`・鍵・個人プロフィールを読まない・映像に載せない
- **環境差**: Windows は Git Bash から同じコマンド(`node` の撮影は Windows でも DevTools のパイプ接続 = Puppeteer と同じ方式。win 2026-10 で Chrome の自動検出・OneDrive 配下の日本語パスとも実走済み)。フォントは OS の日本語ゴシック(Mac = ヒラギノ / Windows = 游ゴシック・メイリオ)なので、文字幅が変わって箱からはみ出すことがある → 静止画で確かめて `w` を広げる(同梱例と 11 場面の新規映像では游ゴシックでもはみ出し無し)。書き出しは CPU 次第で、Windows の数年前の PC では Mac の倍くらいかかる(Core i5-7500 で 70 秒の映像に約 7.5 分 = 約 4.6 コマ/秒)。1.1.0 の絵(インライン SVG と CSS だけ。新しい外部プログラムは無い)は Windows では未実走。文字幅の違いによるはみ出しは「注意」で出るので、それを見て `w` を広げる。TEST-004 の結果に出る `/tmp/...` は Git Bash の表記で、実体は `%TEMP%`
- **固有値の置換表**(買い手に聞く / 空でよい)

| 項目 | 既定 | 備考 |
|---|---|---|
| キャラ | ひまわり猫 8 ポーズ | 差し替え / 無し(§4) |
| 色 | kote2 標準(オリーブ × クリーム × ラストオレンジ) | `theme` で上書き |
| 置き場 | `explainer-videos/{名前}/` | 作業フォルダ直下 |

プレースホルダ(`{{...}}`)は無い(`recipe.json` の `placeholders` は空)。

---

## 10. 完成判定(買い手の AI が自己検証)

§1 機能構成表に対し:
- required(CORE-01〜05)= すべて PASS(1 つでも FAIL なら未完成)
- optional-enabled(FEAT-01)= 頼まれたプロジェクトがあれば PASS / 無ければ SKIP
- optional-disabled(FEAT-02)= SKIP
かつ §5 各 Phase の検証が緑(拡張レシピなので `validate-output.sh` は対象外)。§10 の `recipe-tests/X` はパッケージの `tests/X` を、cwd=ビルダー直下で実行する読み替え。

| TEST ID | 対象 | 種別 | tier | 検証方法 | 期待値 |
|---|---|---|---|---|---|
| TEST-001 | CORE-01 | auto | smoke | `bash recipe-tests/explainer-skeleton.sh` | 14 ファイル・SKILL.md の 1 行目が frontmatter(name / description)・キャラ画像が表どおり・外部 URL の読み込み無し・例と絵の一覧の読み込み先が実在・例が icons.js を読むで PASS(PIT-EV-SKILL-001 の回帰) |
| TEST-002 | CORE-03 | auto | smoke | `bash recipe-tests/explainer-stills.sh` | 例の 2 / 25 / 52 秒目が 1920×1080 の PNG で撮れる(真っ白でない)。ブラウザが無ければ exit 3 = SKIP |
| TEST-003 | CORE-02 | auto | smoke | `bash recipe-tests/explainer-guard.sh` | 無いポーズ・無い矢印・無い箱・無い絵・長さ超えをそれぞれ指摘して exit 非 0、静止画を書き出さない(PIT-EV-GUARD-001 の回帰) |
| TEST-004 | CORE-04 | auto | smoke | `bash recipe-tests/explainer-nocat.sh` | `index.html` から character.js を外しても撮れる |
| TEST-005 | CORE-03 | auto | smoke | `bash recipe-tests/explainer-mp4.sh` | 頭 2 秒の MP4 が 1920×1080・60 コマで書き出せて、コマンドが終わる(PIT-EV-CLOSE-001 の回帰)。ffmpeg が無ければ exit 3 = SKIP(PIT-EV-FFMPEG-001) |
| TEST-006 | FEAT-01 | auto | full | `bash recipe-tests/explainer-project.sh output/{name}` | 写した一式が正本と同じ・CLAUDE.md に 1 行・Codex 両対応ならアダプター(description 一字一句)+ AGENTS.md + check-sync 0 FAIL。スキルの無いプロジェクトは exit 3 = SKIP |
| TEST-007 | CORE-01 | manual | full | ビルダー直下で「〇〇とは を動画で説明して」 | `explainer-videos/{名前}/` に evidence.md(出典 URL・確認日・矢印表)/ plan.md / scene.js / index.html / MP4 がそろい、静止画で文字切れ・重なりが無く、矢印が根拠表と一致する |
| TEST-008 | CORE-05 | auto | smoke | `bash recipe-tests/explainer-icons.sh` | 同梱の絵が 40 個以上・名前は英小文字・意味つき・色を直接書いていない(色クラスで塗る)・使えない要素が無い。絵の一覧(`references/icon-catalog`)を静止画で撮れて、ページのエラーが無い。絵を上に添えて低すぎる箱(上下中央)に「注意: はみ出し」が出て、改行入りの収まる箱には出ない(PIT-EV-FIT-001 の回帰)。ブラウザが無ければ exit 3 = SKIP |

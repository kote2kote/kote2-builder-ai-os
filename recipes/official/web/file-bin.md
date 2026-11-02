<!-- ============================================================ -->
<!-- recipe: file-bin(ファイル便)— URL が鍵・期限付きの自作ギガファイル便      -->
<!-- 由来: 作者の実運用システム(2026-08 時点で本番稼働中)を結晶化。         -->
<!-- 状態: mac/win 両実機で Phase 1〜4 全緑 + 1GB 送受信(MD5 一致)まで実証。 -->
<!--                                                                        -->
<!-- ★固有値を焼かない: ドメイン / 実パス / 氏名 / メール / API キー / デプロイ先  -->
<!--   は本文に一切書かない。買い手ごとに変わる値は §9 の置換表に「何が要るか」だけ。 -->
<!-- ============================================================ -->

# レシピ: file-bin(ファイル便)

手元のファイルをドラッグ&ドロップ(または 1 コマンド)で配布用 URL に変える、自作ギガファイル便を再現するレシピ。
URL を開くとファイル名・サイズ・残り日数の中間ページ → ダウンロード。**約 7 日で自動削除**される。

- 製品名: ファイル便
- 用途分類: Web(ファイル配布インフラ)
- 必要ビルダー VERSION: v3.22.0 以上
- 検証ステータス: `verified` — skeleton(骨組みのみ)/ experimental(未実証)/ verified(実ビルド結晶化済み)。**verified だけが配布対象**。※実運用システムからの結晶化(§5/§6 は実走の一次情報)
- 動作確認: `mac ✅` / `win ✅`(2026-08 実機。Phase 1〜4 全緑 + 1GB MD5 一致 + SendTo 入口)— 実機で建てて緑を取れた OS(クラウド側は OS 無関係、§9)
- 配布元検証: `✅` — 配布元(kote2)が最終サインオフ(2026-08-03。official 配置=検証済みの運用)

姉妹レシピ「html-share-board(社内 HTML 共有ボード)」との関係: 同じ材料(Worker + R2)で性格が真逆。
**ファイル便 = URL が鍵・誰でも開ける・消える** / **共有ボード = 会員制(Access)・一覧に溜まる**。
社外への受け渡しはファイル便、社内の資料棚は共有ボード、と使い分ける。

---

## 1. これは何 / 機能構成 + 完成形(受け入れ基準)

### 機能構成(★ここだけが必須/任意/不採用を決める正本)

| ID | 機能 | 状態 | Phase | 完成判定 |
|---|---|---|---|---|
| CORE-01 | Worker 配信(中間ページ → /dl で元ファイル名ダウンロード。トップ・一覧なし=404) | required | Phase 1 | PASS 必須 |
| CORE-02 | 7 日自動削除(R2 ライフサイクル。削除コードは 1 行も書かない) | required | Phase 1 | PASS 必須 |
| CORE-03 | send.sh(暗号乱数 26 文字の URL 発行 + ローカル送信台帳 + クリップボード) | required | Phase 2 | PASS 必須 |
| CORE-04 | unsend.sh(期限前の取り下げ。非対話実行は `--yes` 必須) | required | Phase 2 | PASS 必須 |
| FEAT-01 | 大容量対応(300MB 超は rclone へ自動フォールバック。1GB 実証済み) | optional-enabled | Phase 3 | enabled なら PASS 必須 |
| FEAT-02 | 送信の入口(mac = droplet app / win = SendTo バッチ) | optional-enabled | Phase 4 | enabled なら PASS 必須 |
| EXCL-01 | 一覧ページ・管理画面 | excluded | — | 作らないこと自体が安全性の根拠(§3) |
| EXCL-02 | ブラウザからのアップロード画面 | excluded | — | 派生(§4)。Access との合わせ技 |
| EXCL-03 | 社内向け資料棚(会員制・一覧に溜まる) | excluded | — | 姉妹レシピ html-share-board へ |

### 完成形(受け入れ基準)
- [ ] required(CORE-01〜04)がすべて緑
- [ ] enabled な optional(FEAT-01/02)がすべて緑(disabled にしたら SKIP=欠落ではない)
- [ ] 送る → 中間ページ → 元ファイル名(日本語も)で落ちる → 7 日で消える(ライフサイクル設定確認)→ unsend で即消せる、が一巡 ← ここまでが「完成」

---

## 2. スタック

| 層 | 採用 | 一行理由 |
|---|---|---|
| 配信 | Cloudflare Workers(TypeScript) | 中間ページ+ダウンロードの 2 ルートだけの極小 Worker |
| 保存 | R2(ライフサイクル 7 日) | 無料枠 10GB・**ダウンロード転送量無料**。期限は R2 の機能=削除コードゼロ |
| ツール | pnpm + wrangler / bash scripts | 送る・取り下げるの出口をスクリプト 2 本に固定 |
| 大容量 | rclone(S3 互換。FEAT-01) | wrangler put の上限(実測 300 MiB)を超える本丸経路 |

- 再現時間の目安: 30 分(**ドメイン不要**。Cloudflare アカウントさえあれば workers.dev で動く)
- ランニングコスト: 0 円から(R2 無料枠 10GB。超えても $0.015/GB・月)

---

## 3. 魔法のタネ(★変えるな。スタック非依存の本質)

- **一覧を作らない(トップも 404)**。「URL を知らないファイルの存在が誰にも見えない」ことが安全性の根拠。
  認証なし = URL が鍵(暗号乱数 26 文字 ≒ 134 ビット)。パスワード保護は捨てた(受け手の手間が増えるだけで、
  URL とパスワードは結局同じ経路で送られる)。
- **メタ情報は R2 オブジェクトだけで完結**(キー = `{id}/{元ファイル名}`)。DB・KV を足さない=部品が減り再現も軽い。
  サイズ・日時は R2 が持っている。
- **削除は「7 日ライフサイクル」+「所有者の unsend」のみ**。受け手側の削除ボタン等は持たない。単純さ優先。
- **「送ったものが見えない」問題はローカル台帳で解決**。送信のたびに日時・名前・URL・状態をローカルファイルに
  記録(git 管理外)。公開側には何も置かないので「一覧を作らない」原則と矛盾しない。
- **サイズで自動分岐**(300MB 以下 = wrangler / 超 = rclone)。ギガファイル便を名乗る以上ここは本丸。
  send スクリプトが自動で選ぶ(使い手に判断させない)。

この 5 点を崩すと「ただのアップローダ」になり、このレシピの安全モデルが消える。

---

## 4. 改変の余地(★変えていい。knob 3分類)

| 分類 | 中身 | 変えると |
|---|---|---|
| **軽量設定** | バケット名 / 404 ページの文言 / 保持日数(prefix 別ライフサイクルで「30 日残る `keep/`」等を追加=実装コードなし) / 独自ドメイン格上げ(★routes と BASE_URL の**2 箇所セット**。片方だけ変えると発行 URL と公開先の食い違い事故。格上げすると配布済み workers.dev URL は無効になる) | 設計を変えずに差し替え可 |
| **機能モジュール** | §1 表の optional-*: rclone 大容量(FEAT-01)/ droplet(FEAT-02。Windows は SendTo バッチの同等品を AI に作らせる) | Phase とテストが増減。§1 表の状態で ON/OFF |
| **派生アーキ** | ブラウザアップロード画面(アップのパスだけ Cloudflare Access で守る=「配る側は門番の内側・受け取る側は URL が鍵」の合わせ技。Worker 経由は 1 リクエスト 100MB 制限があるため大容量は CLI 継続)/ 社内資料棚(姉妹レシピ html-share-board) | **knob ではない**。提案 → ユーザー GO |

---

## 5. 再現の順路(Phase + 検証。実走検証済み)

1 Phase 作る → その場で検証(緑)→ 次へ。一気に作らない。

- **Phase 0 — 生成**: ビルダーでプロジェクト一式(worker/・scripts/)を生成。
  検証(緑): `scripts/validate-output.sh` が 0 FAIL。
- **Phase 1 — セットアップ + デプロイ(CORE-01 / CORE-02)**: `cd worker && pnpm install && pnpm exec wrangler login`
  → `bash scripts/setup-lifecycle.sh`(バケット作成 + 7 日自動削除ルール)→ `pnpm exec wrangler deploy`。
  デプロイ出力の `https://<worker名>.<アカウント名>.workers.dev` を `.env`(`cp .env.example .env`)の `BASE_URL` に貼る。
  検証(緑): `wrangler r2 bucket lifecycle list <バケット名>` に 7 日ルールが出る / URL に適当なパスを付けて開くと 404 ページが出る。
- **Phase 2 — 小ファイルで送受信テスト(CORE-03 / CORE-04)**: `bash scripts/send.sh 適当なファイル.txt`。
  検証(緑): ① URL 発行 + クリップボード ② 中間ページに名前・サイズ・「あと約◯日」 ③ ダウンロードで**元のファイル名**(日本語も化けない)
  ④ `bash scripts/unsend.sh <URL> --yes` で 404 ⑤ ローカル台帳の状態が removed に変わる。
- **Phase 3 — 大容量を有効化(FEAT-01。約 10 分)**: rclone を導入(mac = brew / win = `winget install Rclone.Rclone`)。
  Cloudflare ダッシュボード → R2 → API トークン → **Account API トークン**を作成(権限 = Object Read & Write、対象バケット限定)。
  Access Key / Secret は**使い手が自分の手で** rclone 設定ファイルに貼る(チャット・AI を経由させない)。`.env` に `RCLONE_REMOTE` を設定。
  Access Key / Secret の貼り付け先は、win では入力ヘルパー(PowerShell の Read-Host。Secret は非表示入力)を AI に作らせると
  「トークンをチャットに通さない」原則と両立しやすい。
  検証(緑): 1GB のダミー(`dd if=/dev/zero of=big.bin bs=1m count=1024`)を send して URL から落とし MD5 一致(実測: アップロード mac 81 秒 / win 43 秒)。
- **Phase 4 — 送信の入口(FEAT-02)**: mac = `bash scripts/make-droplet.sh` → できた app を Dock やデスクトップへ。
  win = SendTo バッチ(make-sendto.bat)→ 右クリック →「送る」→ file-bin-send(win 実機検証済み。★PIT-WIN-BAT-001)。
  検証(緑): ドロップ(または右クリック→送る)→ URL 発行 + クリップボード。

---

## 6. 固有の地雷 + 直し方

各地雷は固定 ID(`PIT-{ドメイン}-{3桁}`)+ 確認環境 + 回帰を持つ([templates/recipe/recipe-template.md](../templates/recipe/recipe-template.md) の PIT 規約)。

### [PIT-SHELL-003] ID 生成の `tr < /dev/urandom` + `head` が黙って死ぬ
- 症状: send がエラー表示なしで止まる。
- 原因: `set -euo pipefail` 下では head が切った瞬間 tr が SIGPIPE(exit 141)になる。無限ストリーム+head の組は bash スクリプト共通の地雷。
- 直し方: `(tr … または true)` で吸収してから head に渡し、生成後に文字数を検証する(吸収だけだと短い ID を掴む事故が残るため)。
- 確認環境: mac 実機(2026-08)/ 回帰: TEST-005(吸収イディオムの存在)

### [PIT-WRANGLER-001] wrangler の R2 put は実測 300 MiB が上限
- 症状: 大きいファイルで「Wrangler only supports uploading files up to 300 MiB」。
- 原因: wrangler put がマルチパート非対応。
- 直し方: 300MB 超は rclone(S3 互換・マルチパート対応)へ。send スクリプトがサイズで自動分岐する(FEAT-01)。
- 確認環境: mac 実機(2026-08)/ 回帰: 手動(300MB 級で分岐ログを確認)

### [PIT-WRANGLER-002] `r2 bucket lifecycle add` はルール名が必須
- 症状: ライフサイクル追加がエラーで失敗する。
- 原因: `lifecycle add <bucket> <ルール名> --expire-days 7 --force` の形。名前を省くと落ちる。
- 直し方: setup-lifecycle.sh にルール名を焼き込む。
- 確認環境: mac 実機(2026-08)/ 回帰: TEST-002(スクリプト構文)

### [PIT-CF-WORKERSDEV-001] workers.dev はデプロイ直後だけ 404 を返すことがある
- 症状: 送信直後の疎通確認が 404。ファイルは正常に上がっている。
- 原因: サブドメインの伝播ラグ(数十秒〜数分)。
- 直し方: send の疎通確認はリトライ付きにする。慌てて再アップしない。
- 確認環境: mac 実機(2026-08)/ 回帰: 手動(初回デプロイ直後のみ発生)

### [PIT-SHELL-004] 確認プロンプトが AI の非対話実行で空振りする
- 症状: 「消したつもりで残る」。EOF → set -e で中止扱いになるがエラー表示が出ない。
- 直し方: unsend は非対話+`--yes` なしを**明示エラーで止める**設計にする(黙って中止させない)。
- 備考: 姉妹レシピ html-share-board の unpublish でも同一地雷を確認 → `knowledge/bash.md` へ昇格済み(2026-08。横展開の正はそちら)。
- 確認環境: mac 実機(2026-08)/ 回帰: TEST-006(--yes フラグの存在)

### [PIT-R2-002] R2 API トークンは Account 種別で作る
- 症状: 作った人がアカウントを離れた途端に rclone 経路が全滅する。
- 原因: User 種別トークンは発行者に紐づき、その人の離脱で失効する。
- 直し方: **Account API トークン**で作成し、対象バケットを限定する。
- 確認環境: mac 実機(2026-08)/ 回帰: 手動(§5 Phase 3 の手順書)

### [PIT-WIN-ONEDRIVE-001] OneDrive 配下だと wrangler deploy が「Access is denied」で落ちる
- 症状: 初回デプロイのビルドが `.wrangler\tmp\...\index.js: Access is denied` で失敗。
- 原因: OneDrive の同期がビルド一時ファイルをロックする(OneDrive 配下のプロジェクト共通の地雷)。一過性。
- 直し方: **再実行すれば通る**(このレシピでは `.wrangler/tmp` 削除 + 再実行で成功。姉妹レシピでは削除なしの再実行 3 回目で成功=削除は必須ではない)。頻発するなら `.wrangler` を OneDrive の同期対象外にするか、プロジェクトを OneDrive 外へ。
- 備考: 姉妹レシピ html-share-board でも同一地雷を確認 → `knowledge/windows.md` へ昇格済み(2026-08。横展開の正はそちら)。
- 確認環境: win 実機(2026-08)/ 回帰: 手動(初回デプロイ時のみ発生を確認)

### [PIT-WIN-PS-002] 日本語入り `.ps1` は BOM 無し UTF-8 だと実行前に構文エラーで死ぬ
- 症状: PowerShell スクリプトが起動直後に文字化けした大量のパースエラーを吐く。
- 原因: Windows PowerShell 5.1 は BOM 無し `.ps1` を ANSI(CP932)として読むため、UTF-8 の日本語が化けて構文ごと壊れる。
- 直し方: 日本語を含む `.ps1` は **BOM 付き UTF-8** で保存する(AI 生成ファイルは BOM 無しになりがちなので要注意)。
- 確認環境: win 実機(2026-08)/ 回帰: 手動

### [PIT-WIN-BAT-001] cmd が読む日本語入り `.bat` は CP932 で書く(SendTo 入口の生成)
- 症状: 右クリック→「送る」が「指定されたパスが見つかりません」→ send.sh 不在エラー。
- 原因: UTF-8 コンソール(chcp 65001。AI のシェル経由等)から生成バッチを作ると、中の日本語パスが UTF-8 で書かれ、ダブルクリック時の cmd(CP932)には化けて見える。cmd はバッチをシステムコードページ(日本語環境では CP932)で解釈するため。
- 直し方: 生成側バッチの冒頭に `chcp 932 >nul` を入れて書き込み時の文字コードを固定する(手でダブルクリックした場合も AI 経由でも同じ結果になる)。
- 備考: 姉妹レシピ html-share-board のドロップ用 bat でも同一地雷を確認(そちらは SJIS+CRLF 保存 + chcp 切替の作法を詳述)→ `knowledge/windows.md` へ昇格済み(2026-08。横展開の正はそちら)。
- 確認環境: win 実機(2026-08)/ 回帰: 手動(CP932 の cmd から実送信で確認)

---

## 7. 固有スキル / 道具

- `scripts/send.sh` — 送信の唯一の出口(URL 発行・台帳記録・クリップボード・サイズ自動分岐)
- `scripts/unsend.sh` — 取り下げの唯一の出口(台帳更新つき。非対話は `--yes` 必須)
- `scripts/setup-lifecycle.sh` — バケット作成 + 7 日ライフサイクル(初回のみ)
- `scripts/make-droplet.sh` — macOS ドラッグ&ドロップ app 生成(FEAT-02)
- `make-sendto.bat` — Windows SendTo 入口生成(FEAT-02。CP932 で書く=PIT-WIN-BAT-001)
- ローカル送信台帳 — 日時・名前・URL・状態。git 管理外。「何を送ったか」はここで見る

---

## 8. ハーネス宣言

用途の標準一式を `templates/` から焼く(共通生成ファイル + 自己修復 hooks + rules)。固有の上書きは下記。

- 標準一式: CLAUDE.md / README.md / AGENTS.md / dashboard.html / output-style / commands(self-heal 等)
- ルール: `../templates/rules-secrets.md`(API トークンを扱うため必須)/ `../templates/rules-context-hygiene.md`
- 口調: `../templates/output-style-default.md`
- 固有上書き: worker 一式 / scripts 4 本 / `.env.example` / 送信台帳

---

## 9. 適応指示(環境差・安全側・固有値)

### 環境差
- クラウド側(Worker / R2)は OS 無関係。scripts は bash なので Windows は Git Bash / WSL で実行。
- droplet(FEAT-02)と URL の自動クリップボードコピー(pbcopy)は macOS 専用。Windows は SendTo バッチ(右クリック→「送る」)で同等品を AI に作らせる(win 実機検証済み 2026-08。生成時は PIT-WIN-BAT-001)。コピーは clip.exe で代替。無くても送信は成功する。

### 安全側デフォルト
- 送信済み URL はチャットで送ってよいが、**受け手以外の目に触れる場所(SNS・公開ページ)には貼らない**(URL が鍵そのものなので)。
- 機密度が高いものは、相手の受領を確認して即 unsend(7 日を待たない)。
- rclone のトークンは**使い手が自分の手で**設定ファイルに貼る(チャット・AI を経由させない)。

### 固有値の置換(★実値は焼かない)

| 置き場 | 何の値か | 既定 |
|---|---|---|
| `BASE_URL` | `.env` | 初回デプロイ後に確定した workers.dev URL を貼る(独自ドメイン格上げ時は routes とセットで変更=§4) |
| R2 バケット名 | `.env` / wrangler.jsonc | 汎用名の既定のままで可 |
| R2 API トークン(rclone 用) | rclone 設定ファイル | 空。Account 種別・バケット限定で買い手が作る(PIT-R2-002) |
| Cloudflare アカウント | wrangler login | ブラウザ認可。API キーの受け渡しはしない |

---

## 10. 完成判定(買い手の AI が自己検証)

§1 機能構成表に対し:
- required(CORE-01〜04)= すべて **PASS**(1 つでも FAIL なら未完成)
- optional-enabled(FEAT-01/02)= enabled のものは PASS / disabled にしたものは SKIP
- excluded(EXCL-01〜03)= Phase にもテストにも出さない

かつ `scripts/validate-output.sh` が PASS、§5 各 Phase の検証が緑であること。

### テストマトリクス(機械照合。auto 行は `scripts/recipe-test.sh` が実行)

auto 行は生成スモーク(クラウド疎通・実送受信が要るものは manual)。

| TEST ID | 対象 | 種別 | tier | 検証方法 | 期待値 |
|---|---|---|---|---|---|
| TEST-001 | CORE-01 | auto | smoke | `test -f worker/src/index.ts && test -f worker/wrangler.jsonc` | Worker 一式がある |
| TEST-002 | CORE-02 | auto | smoke | `test -f scripts/setup-lifecycle.sh && bash -n scripts/setup-lifecycle.sh` | ライフサイクル設定の構文 OK |
| TEST-003 | CORE-03 | auto | smoke | `test -f scripts/send.sh && bash -n scripts/send.sh` | 送信スクリプトの構文 OK |
| TEST-004 | CORE-04 | auto | smoke | `test -f scripts/unsend.sh && bash -n scripts/unsend.sh` | 取り下げスクリプトの構文 OK |
| TEST-005 | PIT-SHELL-003 | auto | smoke | `grep -qF "true)" scripts/send.sh` | SIGPIPE 吸収イディオムが入っている |
| TEST-006 | PIT-SHELL-004 | auto | smoke | `grep -qF -- "--yes" scripts/unsend.sh` | 非対話ガード(--yes)がある |
| TEST-007 | CORE-01 | manual | full | send → 中間ページ → 元ファイル名 DL → unsend で 404 → 台帳 removed | 送受信の一巡 |
| TEST-008 | FEAT-01 | manual | full | 1GB ダミーを send → DL → MD5 一致 | 大容量経路 |
| TEST-009 | FEAT-02 | manual | full | mac = droplet にドロップ / win = 右クリック→「送る」→ URL 発行 | 送信の入口 |

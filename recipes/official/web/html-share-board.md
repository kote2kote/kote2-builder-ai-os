<!-- ============================================================ -->
<!-- recipe: html-share-board(社内 HTML 共有ボード → 社内ファイル便)          -->
<!-- 由来: 作者の実運用システム(2026-08 時点で本番稼働中)を結晶化。         -->
<!-- 状態: v1 最小構成 → v2 一覧作り込み → v3 全ファイル対応まで実走済み。     -->
<!--       すべて v1 の設計(キー規約・出口の一本化・認証の外置き)の上に、     -->
<!--       コア構造を変えずに載った = 拡張が設計の検証になっている。           -->
<!--                                                                        -->
<!-- ★固有値を焼かない: ドメイン / 実パス / 氏名 / メール / API キー / デプロイ先  -->
<!--   は本文に一切書かない。買い手ごとに変わる値は §9 の置換表に「何が要るか」だけ。 -->
<!-- ============================================================ -->

# レシピ: html-share-board(社内 HTML 共有ボード)

手元の HTML ファイルを 1 コマンドで「社内(許可したメンバー)限定の URL」にして配り、
公開物が一覧ページにタグ別・日付順で自動整理される仕組みを、自分の環境に再現するレシピ。
全ファイル対応(FEAT-04)まで有効にすると「社内ファイル便」に進化する。

- 製品名: 社内 HTML 共有ボード
- 用途分類: Web(社内共有基盤)
- 必要ビルダー VERSION: v3.22.0 以上
- 検証ステータス: `verified` — skeleton(骨組みのみ)/ experimental(未実証)/ verified(実ビルド結晶化済み)。**verified だけが配布対象**。※実運用システムからの結晶化(§5/§6 は実走の一次情報)
- 動作確認: `mac ✅` / `win ✅` — 実機で建てて緑を取れた OS(win は 2026-08 に CORE-01〜03 の 3 点セット + Windows 版 droplet 同等品(bat)を実走で緑。クラウド側は OS 無関係、§9)
- 配布元検証: `✅` — 配布元(kote2)が最終サインオフ(2026-08-07 更新版で再サインオフ。official 配置=検証済みの運用)

姉妹レシピ「file-bin(ファイル便)」との関係: 同じ材料(Worker + R2)で性格が真逆。
**共有ボード = 会員制(Access)・一覧に溜まる** / **ファイル便 = URL が鍵・誰でも開ける・消える**。
300MB 超の受け渡しはファイル便に分業させると部品が増えない。

---

## 1. これは何 / 機能構成 + 完成形(受け入れ基準)

### 機能構成(★ここだけが必須/任意/不採用を決める正本)

| ID | 機能 | 状態 | Phase | 完成判定 |
|---|---|---|---|---|
| CORE-01 | Worker 配信 + 一覧(キー規約 `pages/{tag}/{date}_{slug}` でタグ別・日付降順。ビルドなしサーバーレンダリング) | required | Phase 1 | PASS 必須 |
| CORE-02 | Access 門番(認証は外置き・Worker にログインコード 0 行・`workers_dev: false` で裏口封鎖) | required | Phase 2 | PASS 必須 |
| CORE-03 | publish.sh / unpublish.sh(公開・取り下げの出口をシェル 2 本に封じる) | required | Phase 3 | PASS 必須 |
| FEAT-01 | 一覧の作り込み(検索・タグ折りたたみ・最近動いたタグ順・NEW バッジ・一覧から取り下げボタン) | optional-enabled | Phase 4 | enabled なら PASS 必須 |
| FEAT-02 | タグの 3 層自動整理(入口で正規化・タグ台帳で再利用・表示で自然淘汰) | optional-enabled | Phase 4 | enabled なら PASS 必須 |
| FEAT-03 | droplet(macOS ドラッグ&ドロップ公開 app) | optional-enabled | Phase 5 | enabled なら PASS 必須 |
| FEAT-04 | 全ファイル対応(HTML=表示 / PDF・画像=ブラウザ内表示 / Office=ダウンロード。旧 URL 互換維持) | optional-enabled | Phase 6 | enabled なら PASS 必須 |
| FEAT-05 | デモデータ機構(demo/ のサンプル + 投入/撤収スクリプトを**同梱**。投入は任意) | optional-disabled | — | 既定 SKIP(投入したら TEST-009) |
| EXCL-01 | 300MB 超の大容量受け渡し | excluded | — | 姉妹レシピ file-bin へ分業 |
| EXCL-02 | 自作ログイン・セッション認証 | excluded | — | Access 外置きが柱(§3)。自作認証は持たない |

### 完成形(受け入れ基準)
- [ ] required(CORE-01〜03)がすべて緑
- [ ] enabled な optional(FEAT-01〜04)がすべて緑(disabled にしたら SKIP / FEAT-05 は既定 SKIP)
- [ ] publish → Access ログイン → 閲覧 → 一覧に載る → unpublish で消える、の 3 点セットが通る ← ここまでが「完成」

---

## 2. スタック

| 層 | 採用 | 一行理由 |
|---|---|---|
| 配信 | Cloudflare Workers(TypeScript) | 一覧も本体も 1 Worker。ビルドパイプラインなし |
| 保存 | R2 単体(メタはキー名に畳む) | KV / D1 を足さない=publish が 1 コマンドで完結する |
| 認証 | Cloudflare Access(メール OTP) | 門番を外置き。人の出入りはポリシー編集だけ・50 席まで無料 |
| ツール | pnpm + wrangler / bash scripts | 出口 2 本(publish / unpublish)に封じる |

- 再現時間の目安: 30〜60 分(Cloudflare アカウントが既にあれば短い側)
- ランニングコスト: 0 円から(Workers / R2 / Access すべて無料枠内で運用可能)
- ドメインなし再現ルート: `workers_dev: true` + workers.dev URL に Access の「Enable Cloudflare Access」ワンクリックで門番を掛ける(§9)

---

## 3. 魔法のタネ(★変えるな。スタック非依存の本質)

骨格は「**負債になりやすい部分を全部外に出す**」こと。

- **キー規約 `pages/{タグ}/{日付}_{名前}.html` がこのレシピの心臓部**。ファイル名だけで「タグ別グルーピング」
  「日付降順」「一覧表示」が成立するので、DB もビルドも要らない。拡張(FEAT 群)もほぼ全部この規約の上に乗る。
- **認証は Access に外置き。Worker にログインコード 0 行**。Basic 認証(共有パスワードは漏れる)も
  自作セッション認証(保守が重く、事故ると全公開)も捨てた。
- **公開・取り下げの出口をシェルスクリプト 2 本に封じる**。複数手順の逐次実行(順番・回数の事故=二重公開・誤削除)を構造で消す。
  入口(droplet 等)を何個増やしても、中身は必ず publish.sh を呼ぶ。
- **`workers_dev: false` で裏口 URL を最初から塞ぐ**。「あとで消す」運用は忘れる。Access を通らない直リンクを残さない。
- **一覧はビルドなしのサーバーレンダリング(CSS 直書き)**。一覧 1 ページにフレームワーク+ビルドは過剰。

この 5 点を崩すと「保守が重い社内 CMS」に戻り、このレシピの価値が消える。

---

## 4. 改変の余地(★変えていい。knob 3分類)

| 分類 | 中身 | 変えると |
|---|---|---|
| **軽量設定** | 公開サブドメイン名 / バケット名 / 一覧の配色・文言 / NEW バッジの日数 / 期限付き公開(R2 ライフサイクルの prefix 指定削除。タグ規約と組めば「temp タグは勝手に消える」が実装コードなしで成立) | 設計を変えずに差し替え可 |
| **機能モジュール** | §1 表の optional-*: 一覧作り込み(FEAT-01)/ タグ 3 層(FEAT-02)/ droplet(FEAT-03。Windows はバッチへのドロップで同等品)/ 全ファイル対応(FEAT-04)/ デモデータ(FEAT-05) | Phase とテストが増減。§1 表の状態で ON/OFF |
| **派生アーキ** | メンバー管理の格上げ(メール列挙 → ドメイン一括 → IdP・グループ連携。Access のポリシー差し替えだけ=コード変更ゼロ)/ ボードを増やす(一式複製 + 固有値 3 点変更 + Access アプリ追加。ボード間は完全独立)/ 「消せる人」を絞る(Access の JWT メールで判定) | 提案 → ユーザー GO |

おまけ(実装不要の隠れ機能): Zero Trust のログで「誰がいつどのページを見たか」は**最初から**見られる。

---

## 5. 再現の順路(Phase + 検証。実走検証済み)

1 Phase 作る → その場で検証(緑)→ 次へ。一気に作らない。

- **Phase 0 — 生成**: ビルダーでプロジェクト一式(worker/・scripts/)を生成。
  検証(緑): `scripts/validate-output.sh` が 0 FAIL。
- **Phase 1 — セットアップ + デプロイ(CORE-01)**: `cd worker && pnpm install && pnpm exec wrangler login`
  → ★deploy 前に衝突チェック: `wrangler deployments list` で同名 Worker が既にないか確認(あれば新規作成ではなく上書きになる。PIT-R2-002 の ②。固有値 3 点を変える)
  → R2 有効化(初回のみダッシュボード。PIT-R2-001)→ `wrangler r2 bucket create <バケット名>`
  → 公開ドメインを自分のものに合わせる(★wrangler.jsonc の routes と scripts の BASE_URL の**2 箇所セット**)→ deploy。
  検証(緑): `curl -s -o /dev/null -w '%{http_code}' https://<公開ホスト>/` が **200**。
  ⚠️ この時点では誰でも見られる。**必ず続けて Phase 2 へ。**
- **Phase 2 — Access 門番(CORE-02。ブラウザで 5 分)**: Zero Trust → Access → Applications → Self-hosted。
  宛先に**フルホスト名**を入力(サブドメイン欄が効かない UI は「カスタム入力に切り替える」)。
  ポリシー: Allow / Emails で許可メールを列挙(自分も忘れずに)。ログインは既定の One-time PIN。
  検証(緑): 同じ curl が **302**(cloudflareaccess.com へのリダイレクト)に変わる。200 のままなら PIT-CF-ACCESS-001。
- **Phase 3 — 初公開テスト(CORE-03)**: `bash scripts/publish.sh テスト.html test`。
  検証(緑): ① 発行 URL でログイン → 見える ② 一覧に 1 件載る ③ `echo y | bash scripts/unpublish.sh <URL>` で消える — の 3 点セット。
  完了直後の一覧は**空が正**(サンプルを見たい時だけ `bash scripts/demo-inject.sh` — 任意。FEAT-05)。
- **Phase 4 — 一覧の作り込み + タグ 3 層(FEAT-01 / FEAT-02)**: 改修は `worker/src/index.ts` の renderIndex **のみ**で完結
  (キー規約にメタが畳んであるため)。検索(クライアントサイド絞り込み)・タグ折りたたみ(localStorage)・
  最近動いたタグ順・7 日以内 NEW バッジ・取り下げボタン(`POST /api/unpublish`。パス検証=`/p/` 始まり・`..` 拒否・2 階層必須。
  門番の内側なので追加認証なし=「閲覧できる人は取り下げもできる」割り切り)。
  タグ 3 層は publish.sh の小文字正規化 + ローカルタグ台帳 + droplet の既存タグ選択式。
  検証(緑): 絞り込み・開閉・並び・バッジ・取り下げが一覧上で動く。
- **Phase 5 — droplet(FEAT-03。macOS)**: AppleScript(`on open` でタグを聞いて publish.sh を呼ぶだけ)を
  `osacompile` で app 化し、Dock やデスクトップへ。PATH は頭で export(PIT-OSA-PATH-001)。
  検証(緑): ドロップ → タグ選択 → URL がクリップボードへ。
- **Phase 6 — 全ファイル対応(FEAT-04)**: 変更は 4 箇所で、キー規約・一覧・認証はそのまま。
  ① publish の拡張子制限を外し MIME 決定(**Office 系は file コマンドだと zip 判定になる**ので拡張子→MIME 対応表で明示)
  ② キー規約を `{date}_{slug}.{ext}` に一般化(旧形式の拡張子なし URL は Worker が .html を補って互換維持=配布済みリンクを壊さない)
  ③ 配信分岐: HTML=表示 / PDF・画像・テキスト=ブラウザ内表示 / Office 等=ダウンロード(RFC 6266 で元ファイル名復元)
  ④ 一覧に種類バッジ。サイズ上限は wrangler put の実測 300 MiB(超は姉妹レシピ file-bin へ)。
  検証(緑): PDF がブラウザ内で開く / Excel が元ファイル名で落ちる / 旧 URL が生きている。

> FEAT-05(デモデータ)は**既定 SKIP = セットアップ直後の一覧は空**。ただし**機構(demo/ のサンプル + demo-inject.sh /
> demo-remove.sh)は必ず同梱**し、使い手が「サンプルを入れて」と言えばいつでも投入できる(紹介・検証・練習用)。
> ※2026-08 に一度「既定 ON」を試したが、紹介動画が「空の一覧」で撮影されたため既定 SKIP に確定(見せる体験と買い手の
> 実体験を一致させるという判断基準そのものは変えていない)。
> 投入(demo-inject.sh)は publish の出力 URL を記録ファイル(.demo-ledger)に残し、撤収(demo-remove.sh)はそれ**だけ**を
> 取り下げる(本物のデータを巻き込まない)。日付は `PUBLISH_DATE=YYYY-MM-DD` 上書きでばらし、日付順・NEW バッジが見える状態にする。

---

## 6. 固有の地雷 + 直し方

各地雷は固定 ID(`PIT-{ドメイン}-{3桁}`)+ 確認環境 + 回帰を持つ([templates/recipe/recipe-template.md](../templates/recipe/recipe-template.md) の PIT 規約)。

### [PIT-R2-001] R2 未有効化でバケット作成が `code: 10042` で失敗する
- 症状: CLI からのバケット作成が謎コードで落ちる。
- 原因: R2 はダッシュボードでの有効化(+支払い方法登録)が先。無料枠 10GB があり、この用途ではまず無料範囲。
- 直し方: ダッシュボード → R2 → Get started を済ませてから CLI に戻る。README 手順に載っていないことが多い。
- 確認環境: mac 実機(2026-08)/ 回帰: 手動(§5 Phase 1 の手順書)

### [PIT-R2-002] バケット作成が `code: 10004`(自分所有の同名あり)— ★続行前に既存システムとの衝突を疑う
- 症状: `wrangler r2 bucket create` が「already exists, and you own it [code: 10004]」で落ちる。
- 原因は 2 通りで、見分けずに続行すると事故になる:
  ① **同じプロジェクトの再セットアップ・リトライの残り** → 続行してよい(create が冪等でないだけ)。
  ② **同じアカウントに同名の稼働中システムが既にある** → このまま deploy すると新規作成ではなく**既存 Worker の上書き + バケット共有**になる。「2 台目のボードを建てたつもりが本番を上書きしていた」実事故あり(独自ドメインは Worker に残るため、気づくのは「別々のはずの URL が同じ内容を出す」時)。
- 直し方: 続行の前に `wrangler deployments list` で同名 Worker の作成日時を確認する。**このセットアップより古い日付があれば ②**。固有値 3 点(Worker 名 / バケット名 / BASE_URL)を変えてから deploy する(§4 派生アーキ「ボードを増やす」と同じ手順)。
- 確認環境: win 実機(2026-08。① と ② の両方を実走で確認)/ 回帰: 手動(§5 Phase 1 の手順書)

### [PIT-CF-ZONE-001] ゾーン外ドメインで deploy が `Could not find zone` で失敗
- 症状: routes に書いたドメインで deploy が止まる。
- 原因: custom_domain は**そのゾーンが自分の Cloudflare アカウントにあること**が前提。
- 直し方: `dig +short NS <domain>` で NS が `*.ns.cloudflare.com` かを即判定。外なら ① アカウント内の別ゾーンのサブドメインに変える(2 箇所セット書き換えで数分)② ゾーンごと移管(NS 変更で数時間〜)。急ぐなら ①。
- 確認環境: mac 実機(2026-08)/ 回帰: 手動(Phase 1 で判定コマンドを先に打つ)

### [PIT-CF-ACCESS-001] Access が効かない(curl が 200 のまま)
- 症状: 門番を設定したのに誰でも見える。
- 原因: アプリの宛先がサブドメイン抜けで apex だけ守っている典型。
- 直し方: 宛先がフルホスト名そのものかを確認。サブドメイン入力欄が効かない UI の時は「カスタム入力に切り替える」。
- 確認環境: mac 実機(2026-08)/ 回帰: TEST-005(302 確認は手動、手順書に明記)

### [PIT-SHELL-004] unpublish の確認プロンプトが非対話実行で空振りする
- 症状: AI・cron から実行すると**エラー表示なしで中止扱い**になり、消えていないことがある。
- 原因: `[y/N]` プロンプトが EOF を受けて中止扱いになる。
- 直し方: `echo y |` を前置し、実行後に消えたことを確認する。
- 備考: 姉妹レシピ file-bin の unsend でも同一地雷を確認 → `knowledge/bash.md` へ昇格済み(2026-08。横展開の正はそちら)。
- 確認環境: mac 実機(2026-08)/ 回帰: 手動(手順書の削除確認)

### [PIT-OSA-PATH-001] droplet の AppleScript から publish.sh が動かない
- 症状: ターミナルでは動くのに app からだと失敗する。
- 原因: `do shell script` の PATH はほぼ空。pnpm / node が見つからない。
- 直し方: スクリプト冒頭で pnpm / node の場所を export してから publish.sh を呼ぶ。
- 確認環境: mac 実機(2026-08)/ 回帰: 手動(FEAT-03 有効時のドロップテスト)

### [PIT-WIN-PY-001] Windows で validate-codex の config.toml 検査が FAIL する(python3 が Store スタブ)
- 症状: 生成後の検証ゲート `validate-codex.sh` が「Codex CLI がないため config.toml を厳密検査できない」で FAIL。プロジェクト自体は正常。
- 原因: Windows では `python3` が Microsoft Store のスタブ(実行できない空殻)に解決されることがあり、tomllib ルートが使えない。Codex CLI 未導入だとフォールバック先も無く FAIL に落ちる。
- 直し方: 実体の Python 3.11+ を `python3` として見せてから再実行する(例: 実体 python.exe への `python3` シェルシムを PATH 先頭に置く。winget の Python 導入でも可)。検査のスキップではなく正規の TOML parser ルートを有効化するのが筋。
- 確認環境: win 実機(2026-08。Phase 0 生成時)/ 回帰: 手動(生成直後の validate-codex 実行)
- 備考: このレシピ固有ではなくビルダーの Codex 両対応生成全般で踏む(Windows + Codex CLI 無し)。model-bench でも既出(同 ID)→ `knowledge/windows.md` へ昇格済み(2026-08。横展開の正はそちら)。

### [PIT-WIN-BAT-001] ドロップ用 bat の日本語が文字化けする(UTF-8 保存が原因)
- 症状: Windows 版 droplet 同等品(bat へのドラッグ&ドロップ)で、案内文・タグ入力プロンプトの日本語が化ける。
- 原因: cmd.exe はバッチファイルをシステムコードページ(日本語環境では CP932)で解釈するため、UTF-8 で保存した bat の日本語リテラルは化ける。冒頭で `chcp 65001` してもファイル自体の解釈は救えない。
- 直し方: bat 本体は **Shift-JIS(CP932)+ CRLF で保存**する。UTF-8 が必要なのは bash 側の出力だけなので、`publish.sh` 呼び出しの**間だけ** `chcp 65001` に切り替え、終わったら `chcp 932` に戻す。
- 補足 1(化けの実害): 化けは見た目だけでは済まない。化けたバイト列に `&` が現れると cmd がコマンド区切りと誤解釈し、**文字列の破片が別コマンドとして実行される**(「'ot' は認識されていません」の嵐)。表示問題ではなく実行事故として扱う。
- 補足 2(ERRORLEVEL): `chcp` は ERRORLEVEL をリセットする。bash 呼び出し直後に `set "RC=%ERRORLEVEL%"` で退避してから `chcp 932` に戻し、成否判定は RC で行う(忘れると失敗が常に成功表示になる)。
- 回帰の自動化: `printf '<タグ>\ny\n' | cmd //c tools\publish-drop.bat <ファイル絶対パス>` で D&D 相当を非対話実行できる(`set /p` と `pause` が標準入力から拾う)。コンソール出力は CP932/UTF-8 混在で化けるため、成否は表示ではなく **R2 実体**(`wrangler r2 object get` で在る/無い)で確認する。
- 備考: 姉妹レシピ file-bin の SendTo 入口生成でも同一地雷を確認(そちらは生成側 `chcp 932` 固定の作法)→ `knowledge/windows.md` へ昇格済み(2026-08。横展開の正はそちら)。
- 確認環境: win 実機(2026-08。FEAT-03 の Windows 同等品。実走で修正・ドロップ公開 → 取り下げまで緑)/ 回帰: 上記の非対話実行 + 日本語表示の目視

### [PIT-WIN-ONEDRIVE-001] OneDrive 配下で `wrangler deploy` が「Access is denied」で失敗する
- 症状: deploy のビルドが「Failed to write to output file …\.wrangler\tmp\deploy-…\index.js: Access is denied」で落ちる。コード・設定は正しいのに失敗する。
- 原因: プロジェクトが OneDrive 同期フォルダ(デスクトップ等)にあると、deploy が毎回作る一時フォルダを OneDrive が掴んだ瞬間、esbuild の書き出しが拒否される。同期ロックによる**一過性**の失敗(Defender のフォルダーアクセス制御が無効でも起きる)。
- 直し方: **そのまま再実行**(実測: 2 連続失敗 → 3 回目で成功。`.wrangler/tmp` の削除は効果なし)。頻発する場合は `.wrangler` を OneDrive の同期対象から外すか、プロジェクトを OneDrive 外に置く。
- 備考: 姉妹レシピ file-bin でも同一地雷を確認 → `knowledge/windows.md` へ昇格済み(2026-08。横展開の正はそちら)。
- 確認環境: win 実機(2026-08。Phase 1)/ 回帰: 手動(手順書に「Access is denied は再実行」と明記)

---

## 7. 固有スキル / 道具

- `scripts/publish.sh` — 公開の唯一の出口(タグ小文字正規化・タグ台帳記録・クリップボード)
- `scripts/unpublish.sh` — 取り下げの唯一の出口
- droplet app(FEAT-03)— AppleScript。タグを既存台帳から選択式で聞く(新規タグは明示選択の時だけ)
- デモデータ機構(FEAT-05)— `demo/` のサンプル数点 + `scripts/demo-inject.sh` / `scripts/demo-remove.sh`(中身は publish.sh / unpublish.sh を呼ぶだけ=出口の一本化を維持)
- ローカルタグ台帳 — 公開のたびに使ったタグを自動記録(タグ分裂 `Client-A`/`client-a`/`クライアントA` を構造で防ぐ)

---

## 8. ハーネス宣言

用途の標準一式を `templates/` から焼く(共通生成ファイル + 自己修復 hooks + rules)。固有の上書きは下記。

- 標準一式: CLAUDE.md / README.md / AGENTS.md / dashboard.html / output-style / commands(self-heal 等)
- ルール: `../templates/rules-secrets.md` / `../templates/rules-context-hygiene.md`
- 口調: `../templates/output-style-default.md`
- 固有上書き: worker 一式 / scripts 2 本 / droplet ソース(FEAT-03)/ デモデータ一式(FEAT-05)

---

## 9. 適応指示(環境差・安全側・固有値)

### 環境差
- 核心(Worker / R2 / Access)はクラウド側なので **OS を選ばない**。scripts は bash なので Windows は Git Bash / WSL で実行。
- droplet(FEAT-03)は macOS 専用。Windows は「バッチファイルへのドラッグ&ドロップ」で同等品を AI に作らせる(bat は Shift-JIS + CRLF で保存。PIT-WIN-BAT-001)。
- Windows の生成後検証は実体の Python 3.11+ が要る(`python3` が Store スタブだと validate-codex が FAIL。PIT-WIN-PY-001)。
- Windows でプロジェクトを OneDrive 配下(デスクトップ等)に置くと、deploy が同期ロックで一時的に失敗することがある(再実行で通る。PIT-WIN-ONEDRIVE-001)。
- pbcopy(クリップボード)は macOS 専用。無い環境ではスキップされるだけで公開は成功する(Windows は `clip` へ差し替え)。
- 日本語ファイル名のデモ素材は、古い Git Bash だと表示が化けることがある(ファイル自体は正常)。

### ドメインを持っていない場合(無料で再現するルート)
`wrangler.jsonc` の `workers_dev` を `true` にして routes を消し、無料の workers.dev URL で運用する。門番はダッシュボード →
対象 Worker → Settings → Domains & Routes → workers.dev の「**Enable Cloudflare Access**」ワンクリック。
入口が workers.dev の 1 つだけなので「入口を 1 つに絞る」原則は保たれる。後から独自ドメインへ格上げする時は、
routes 追加 + BASE_URL 変更(2 箇所セット)+ workers_dev 無効化 + Access アプリを新ホスト名で作り直す。

### 安全側デフォルト
- Phase 1 直後は誰でも見られる状態。**Phase 2(門番)を終えるまで実データを publish しない**。
- 許可メールアドレス群はコード・レシピに書かない(Access ポリシー側で管理)。
- 見せ終わった下書きは取り下げて掃除(unpublish が気軽に叩けるのはこのため)。

### 固有値の置換(★実値は焼かない)

| 置き場 | 何の値か | 既定 |
|---|---|---|
| 公開ドメイン | wrangler.jsonc の routes / scripts×2 の BASE_URL | **必ず 2 箇所セットで変更** |
| R2 バケット名 | wrangler.jsonc / scripts×2 の BUCKET | 汎用名の既定のままで可 |
| 許可メールアドレス群 | Access ポリシー | Zero Trust 画面で列挙(自分も忘れずに) |
| Cloudflare アカウント | wrangler login(ブラウザ認可) | API キーの受け渡しはしない |

---

## 10. 完成判定(買い手の AI が自己検証)

§1 機能構成表に対し:
- required(CORE-01〜03)= すべて **PASS**(1 つでも FAIL なら未完成)
- optional-enabled(FEAT-01〜04)= enabled のものは PASS / disabled にしたものは SKIP
- optional-disabled(FEAT-05)= 既定 **SKIP**。ただし機構(demo/ + 投入/撤収スクリプト)は同梱する(投入したら TEST-009 で確認)
- excluded(EXCL-01/02)= Phase にもテストにも出さない

かつ `scripts/validate-output.sh` が PASS、§5 各 Phase の検証が緑であること。

### テストマトリクス(機械照合。auto 行は `scripts/recipe-test.sh` が実行)

auto 行は生成スモーク(クラウド疎通・Access 実認証が要るものは manual)。

| TEST ID | 対象 | 種別 | tier | 検証方法 | 期待値 |
|---|---|---|---|---|---|
| TEST-001 | CORE-01 | auto | smoke | `test -f worker/src/index.ts && test -f worker/wrangler.jsonc` | Worker 一式がある |
| TEST-002 | CORE-02 | auto | smoke | `grep -q workers_dev worker/wrangler.jsonc` | 裏口封鎖の設定が明示されている |
| TEST-003 | CORE-03 | auto | smoke | `bash -n scripts/publish.sh && bash -n scripts/unpublish.sh` | 出口 2 本の構文 OK |
| TEST-004 | CORE-01 | manual | full | deploy 後に公開ホストへ curl → 200(門番設定前) | 配信が成立 |
| TEST-005 | CORE-02 | manual | full | 門番設定後に同じ curl → 302(cloudflareaccess へ) | 全入口に門番が効く |
| TEST-006 | CORE-03 | manual | full | publish → ログイン閲覧 → 一覧 1 件 → unpublish で消える | 3 点セット |
| TEST-007 | FEAT-01 | manual | full | 検索・折りたたみ・タグ順・NEW バッジ・取り下げボタン | 一覧 UX が動く |
| TEST-008 | FEAT-04 | manual | full | PDF=ブラウザ内表示 / Office=元ファイル名 DL / 旧 URL 互換 | 全ファイル対応 |
| TEST-009 | FEAT-05 | manual | full | demo-inject → 一覧にサンプル 4 件 → demo-remove → サンプルだけ消える | 投入と撤収が対で動く |

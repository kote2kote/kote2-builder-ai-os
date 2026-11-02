<!-- ============================================================ -->
<!-- recipe-sandbox-handson — 設計書(シード)= Claude Code サンドボックス体験道場 -->
<!-- 由来: 実ビルドを結晶化 — Claude Code 自身のサンドボックス機能を、       -->
<!--       「箱なし vs 箱あり」の対比で体感する学習ラボ(2026-06)。          -->
<!--       実機(macOS 26.5 / Claude Code 2.1.170)で建て、実験を当事者が     -->
<!--       走らせて壁の発火を確認。設定キーは実機バイナリから直接抽出。      -->
<!-- バージョンは git で管理(ファイル名に付けない)。                       -->
<!-- 状態: 単体レシピ。CORE は macOS で verified。Linux は §9 で吸収(枠)。  -->
<!-- ★作者固有値(絶対パス / ホーム実体 / メール / API キー)は本文に焼かない。 -->
<!--   すべてプレースホルダ({builder-folder} / ~ )。                        -->
<!-- ============================================================ -->

# recipe-sandbox-handson — Claude Code サンドボックスを「箱なし vs 箱あり」で体感する学習道場

Claude Code 自身の**サンドボックス機能**(Bash の OS レベル隔離)を、壊しても平気な隔離ラボで**手を動かして**理解する設計書(シード)。座学ではなく、同じ実験を「箱なし(素)」と「箱あり(隔離)」の2セッションで走らせて**対比で腹落ちさせる**のが核。

- 製品名: サンドボックス体感道場
- 用途分類: **学習 / ハンズオン教材**(成果物=理解 + 再利用できるデモ環境)
- 必要ビルダー VERSION: 3.7.1
- 検証ステータス: `verified` — skeleton(骨組みのみ)/ experimental(未実証)/ verified(実ビルド結晶化済み)。**verified だけが配布対象**。※ CORE は macOS で実ビルド+実験発火を確認。Linux バックエンド(bubblewrap)は未検証で §9 に吸収手順のみ。
- 動作確認: `mac ✅` / `win ⬜` — 実機で建てて緑を取れた OS(⬜=未検証=動かない確証ではない。Linux バックエンドも未検証=§9)
- 配布元検証: `✅` — 配布元(kote2)が最終サインオフ(2026-08-03。official 配置=検証済みの運用)
- **この設計書の肝(1)**: 「箱なし vs 箱あり」を**2つの並走セッション**で見せる。同じスクリプトが、起動した場所と設定で正反対の結果(漏れる/弾かれる)を出す。これが最大の教育効果。
- **この設計書の肝(2)**: 「**壁**(`enabled`)」と「**確認の削減**(`autoAllowBashIfSandboxed`)」が別レイヤーだと、設定を1つずつ切り替えて体感させる。混同が一番起きるポイントを構造で解く。

---

## 1. これは何 / 機能構成 + 完成形(受け入れ基準)

Claude Code に話しかけてスクリプトを走らせるだけで、サンドボックスの「ファイルの壁」「ネットの壁」「脱出ハッチ」を、箱なしの素の挙動と対比しながら体で理解できる。

### 機能構成(★ここだけが必須/任意/不採用を決める正本。他章はこの表を参照する)

| ID | 機能 | 状態 | Phase | 完成判定 |
|---|---|---|---|---|
| CORE-01 | サンドボックス有効化(`.claude/settings.local.json` に `enabled` + `autoAllowBashIfSandboxed`。実機準拠キー) | required | Phase 1 | PASS 必須 |
| CORE-02 | ファイルの壁の実験(砂場の中=通る / 外=ブロック。`01`/`02` スクリプト + `playground/`) | required | Phase 2 | PASS 必須 |
| CORE-03 | ネットの壁の実験(未許可ドメイン=遮断。`03` スクリプト) | required | Phase 3 | PASS 必須 |
| CORE-04 | ハンズオン手順書(`manual.html`。箱なし/箱あり対比の進行を図解) | required | Phase 4 | PASS 必須 |
| FEAT-01 | 発展編(穴あけ=`allowedDomains`/`allowWrite` / プロンプト復活=`autoAllow false` / 鉄壁モード=`allowUnsandboxedCommands false`) | optional-enabled | Phase 5 | enabled なら PASS 必須 |
| EXCL-01 | Cloudflare Sandbox SDK(Workers 上のコード隔離 SDK。名前が似た別物) | excluded | — | 別領域(混同注意) |
| EXCL-02 | 本番業務での常用サンドボックス設定の作り込み | excluded | — | これは学習専用ラボ。運用設計は別 |

> 状態語彙は `required / optional-enabled / optional-disabled / excluded` の 4 つだけ。

### 完成形(受け入れ基準)
- [ ] `required`(CORE-01〜04)がすべて緑(箱ありセッションで:`02` がホーム書込を `Operation not permitted` で弾く / `03` が未許可ドメインに繋がらない / `manual.html` がブラウザで開ける)
- [ ] **箱なし(素のセッション)と箱あり(ラボ起動)で、`02`・`03` の結果が正反対**になることを確認できる(対比が成立 = この教材の合格条件)
- [ ] ← ここまでが「完成」。FEAT-01(発展編)は任意で深掘り

## 2. スタック

| 層 | 採用 | 備考 |
|---|---|---|
| 隔離バックエンド | **OS 組み込み**(macOS=Seatbelt / Linux・WSL2=bubblewrap + socat) | macOS は追加インストール不要。Linux は §9 参照 |
| 設定 | `.claude/settings.local.json`(`sandbox.*`) | プロジェクト限定・gitignore 対象。PC 全体に影響させない |
| 実験 | 素の **Bash スクリプト**(`curl` / ファイル書込) | 学習に集中するため最小。言語ランタイム不要 |
| 教材 | 単一 **HTML**(`manual.html`) | 図解付き手順書。人間が参照するものは HTML 化(ai-behavior 準拠) |

> 前提: Claude Code **2.1.x** 系(`sandbox.*` キー実装済み)。設定キー名はバージョン依存しうる(§6・§9)。

## 3. アーキの肝 = 魔法のタネ(★変えちゃダメ)

ここを崩すと「ただ設定を眺めるだけ」or「壁が体感できない座学」に戻る。再現必須:

1. **2セッション並走の対比**: 「箱なし(親フォルダ等・サンドボックス OFF)」と「箱あり(ラボフォルダで起動・ON)」で**同じスクリプトを走らせて結果を見比べる**。サンドボックスが**セッション単位・起動時決定**であることを、並走そのもので体感させる。
2. **壁と確認削減を分離して見せる**: `enabled`(壁)はそのままに `autoAllowBashIfSandboxed` だけ true↔false すると、「同じ壁・同じ書ける場所・聞かれ方だけ変わる」が観察できる。**この2つは別機能**を体で分からせる(最大の誤解ポイント)。
3. **「全部禁止 → 必要な穴だけ許可」**: 既定は何も通さない。`network.allowedDomains` / `filesystem.allowWrite` で**狙った穴だけ**あけて通す感覚を握らせる。
4. **設定キーは実機準拠(推測しない)**: 教材に載せるキーは推測で書かず、実機の挙動・公式仕様で裏取りしたものだけ使う。
5. **壊しても平気な隔離ラボ**: 設定は `settings.local.json`(gitignore・プロジェクト限定)。実験の失敗・漏れがユーザーの PC 全体に波及しない安全圏を最初に作る。

> ★この §3 は環境非依存の「型」。OS が macOS 以外でも、隔離バックエンド(§2)を読み替えるだけで「対比 / 壁と確認削減の分離 / 穴あけ / 隔離ラボ」の骨格は保つ。

## 4. 改変の余地(★変えていい。ヒアリングして見せてから建てる。サイレント適用しない)

### 軽量設定(設計を変えず差し替え)
- **実験の対象ドメイン**(`03`): 既定 `example.com` ↔ 任意の検証用ドメイン。サイレント適用可。
- **手順書の言語・トーン**: 既定は日本語・非エンジニア向け。受講者層に合わせて調整可。
- **砂場の外ターゲット**(`02`): 既定はホーム直下のマーカーファイル。別の「箱外パス」に変更可。

### 機能モジュール(§1 表の optional-* で ON/OFF)
- **FEAT-01 発展編**: 穴あけ / プロンプト復活 / 鉄壁モードの3点。短時間デモなら disabled、講座本編なら enabled。

### 派生アーキ(knob ではない。提案 → GO)
- **Linux / WSL2 向けラボ**: 隔離バックエンドが bubblewrap + socat になり、導入 Phase が増える(§9)。魔法のタネ(§3)は移植、環境セットアップ層は作り直し。

## 5. 再現の順路(Phase + 各段の検証)★最重要

1 Phase ごとに作る → その場で緑を確認 → 次へ。一気に作らない。

- **Phase 0 — 環境確認(緑: 隔離バックエンドが使えると分かる)**
  - `claude --version`(2.1.x 系)/ OS 確認 / 既存 `~/.claude/settings.json` に sandbox 設定が無いことを確認。
  - macOS なら Seatbelt 内蔵=追加インストール不要。Linux は §9 の前提を満たすか確認。
- **Phase 1 — CORE-01: 箱を ON(緑: `settings.local.json` が妥当な JSON)**
  - `.claude/settings.local.json` に `{"sandbox":{"enabled":true,"autoAllowBashIfSandboxed":true}}` を置く。
  - 検証: JSON パースが通る。**この設定は起動時に効く**ことを手順書に明記(§6 地雷)。
- **Phase 2 — CORE-02: ファイルの壁(緑: 中=成功 / 外=ブロック)**
  - `playground/sketch.txt`(中の的)、`experiments/01-write-inside.sh`(中へ追記)、`experiments/02-write-outside.sh`(ホームへ書込試行)を作る。
  - 検証: 箱ありセッションで `01`=成功・`02`=「ブロックされました」。箱なしでは `02`=漏れる(対比)。
- **Phase 3 — CORE-03: ネットの壁(緑: 未許可ドメイン=遮断)**
  - `experiments/03-network.sh`(未許可ドメインへ `curl`)を作る。
  - 検証: 箱ありで「繋がりませんでした」。箱なしで「繋がりました」(対比)。
- **Phase 4 — CORE-04: 手順書(緑: ブラウザで開け、対比進行が追える)**
  - `manual.html`(箱なし/箱あり対比、STEP 0〜7、設定キー早見表、Mac 地雷、後始末)を作る。
  - 検証: 主要ファイル(README / manual)にプレースホルダが残っていない。
- **Phase 5(FEAT-01 が enabled の時)— 発展編**
  - 穴あけ(`network.allowedDomains` に対象ドメイン → `03` が繋がる)/ プロンプト復活(`autoAllowBashIfSandboxed:false` → 箱の中でも確認が出る)/ 鉄壁モード(`allowUnsandboxedCommands:false` → コマンド単位の脱出を封印)。
  - 検証: 各設定変更後に**開き直して**から実験し、期待挙動が出る。

## 6. 固有の地雷 + 直し方(★実ビルドで踏んだ地雷を結晶化。逆抽出では拾えないプロセス知)

各地雷は固定 ID(`PIT-{ドメイン}-{3桁}`)+ 確認環境 + 回帰を持つ([templates/recipe/recipe-template.md](../templates/recipe/recipe-template.md) の PIT 規約)。

- **[PIT-CC-SANDBOX-001] 地雷①: 設定が効かない**
  - 症状: `settings.local.json` を書いたのに壁が発火しない。
  - 原因: **サンドボックスの ON/OFF はセッション起動時にしか読まれない**。
  - 直し方: 設定変更後は **Claude Code を開き直す**。手順書の各 STEP に「`/exit` → `claude`」を明記。
  - 確認環境: mac 実機(2026-06)/ 回帰: 手動(manual.html の各 STEP に開き直しがあるか)
- **[PIT-CC-SANDBOX-002] 地雷②(最重要): `allowUnsandboxedCommands` がネットのプロンプトを消すと誤認**
  - 症状: 「鉄壁モード(`allowUnsandboxedCommands:false`)にすれば『Network request outside of sandbox』プロンプトが消える」と説明 → 消えない。
  - 原因: **「箱の外でやる」には2系統あり別物**。①コマンド単位の脱出(`dangerouslyDisableSandbox` パラメータ。表示=`Run outside of the sandbox`)を司るのが `allowUnsandboxedCommands`。②ネット接続の承認(表示=`Network request outside of sandbox`)は**ネット許可リスト側**の担当で、`allowUnsandboxedCommands` とは無関係。
  - 直し方: 教材では2系統を**最初から分けて**説明する。ネットのプロンプトを黙らせたいなら `network.deniedDomains` / `allowManagedDomainsOnly` 側で制御(コマンド脱出の設定ではない)。
  - 確認環境: mac 実機(2026-06)/ 回帰: 手動(manual.html が 2 系統を分けて説明しているか)
- **[PIT-CC-SANDBOX-003] 地雷③: 「Auto mode」と「auto-allow」の名前混同**
  - 症状: 許可モードの「Auto mode」と、サンドボックスの「auto-allow(`autoAllowBashIfSandboxed`)」を同一視。
  - 直し方: 「**中身で判断するのが Auto mode、檻に入ってるかで判断するのが auto-allow**」と対で教える。別レイヤー(許可モード=全ツール共通の方針 / サンドボックス=OS の壁)。
  - 確認環境: mac 実機(2026-06)/ 回帰: 手動(教材の用語説明)
- **[PIT-CC-SANDBOX-004] 地雷④: 実験スクリプトが失敗を握りつぶすと、コマンド脱出が観察できない**
  - 症状: `02`/`03` を `if ... 2>/dev/null` で握って exit 0 にすると、AI から見て「成功」になり、`allowUnsandboxedCommands` の効果(`Run outside of the sandbox` 提示)が出ない。
  - 直し方: 壁そのものの体感(中/外・ネット)は握りつぶし版でよい。**コマンド脱出を見せたい時だけ**、握らない生コマンドを直接 AI に頼む。
  - 確認環境: mac 実機(2026-06)/ 回帰: 手動(脱出デモ時は生コマンド)
- **[PIT-CC-SANDBOX-005] 地雷⑤: Linux で壁が立たない**
  - 症状: Linux/WSL2 で sandbox 有効なのに隔離されない。
  - 原因: bubblewrap / socat 未導入(macOS は Seatbelt 内蔵で不要)。
  - 直し方: §9 の Linux 手順。`/sandbox` が依存タブのみ表示なら、導入後に開き直して再検出。
  - 確認環境: 未検証(Linux は §9 の枠のみ)/ 回帰: —(Linux 実走時に更新)

## 7. 固有スキル / 道具(ビルダー標準テンプレに無い同梱物)

- `experiments/01-write-inside.sh` / `02-write-outside.sh` / `03-network.sh` — 壁を体感する最小スクリプト3本(実行権限付与)。
- `playground/sketch.txt` — 「砂場の中」の追記先(中=通るの的)。
- `manual.html` — 箱なし/箱あり対比のハンズオン手順書(教材本体)。

## 8. ハーネス宣言(実体はビルダー templates/ が供給)

シードは宣言だけ。ハーネス本体はビルダーが焼く:

- **標準ハーネス一式(`CLAUDE.md` / `AGENTS.md` / `.gitignore` / `.claude/settings.json` / dashboard / secrets / context-hygiene / revisions 等)はビルダーが必ず配置する**(全プロジェクト共通の土台 = `validate-output.sh` の必須。学習用途でも省かない)。
- **このレシピ固有の追加は最小**: `.claude/settings.local.json`(サンドボックス設定が主役。標準の `settings.json` とは別ファイル)/ `experiments/` の3スクリプト / `playground/` / `manual.html`。「最小」は固有追加が少ないという意味で、標準ハーネスを省く意味ではない。
- `README.md` は入口 + 安全注意(これはこのフォルダ限定の設定 / 漏れた `LEAK` ファイルの後始末)。

## 9. 適応指示(環境差の吸収 + 安全側デフォルト + 個人データ剥離)★最重要

### 環境差
- **macOS**: Seatbelt 内蔵。追加インストール不要(verified)。
- **Linux / WSL2**: `bubblewrap` と `socat` を導入(`apt-get install bubblewrap socat` 等)。任意で `@anthropic-ai/sandbox-runtime`。導入後に Claude Code を開き直して再検出。
- **Windows ネイティブ**: 非対応。WSL2 を使う。

### 安全側デフォルト
- 設定は必ず **`.claude/settings.local.json`**(プロジェクト限定・gitignore)。`~/.claude/settings.json`(全 PC 共通)はラボでは触らない。
- ネットは既定で**全遮断**(`allowedDomains` 空)。穴は最小限・明示的に。
- 実験で漏れる可能性のあるマーカー(`02` のホーム書込)は、後始末コマンドを README と手順書に明記。

### 固有値の置換(★焼かない)
| 焼かない実値 | 置換 |
|---|---|
| ビルダー本体の絶対パス | `{builder-folder}`(実行時に `**/builder.md` から取得) |
| ホームの実体パス | `~`(`$HOME`) |
| 実在のメール / API キー / 社内ドメイン | 載せない(教材に不要) |
| 検証ドメイン | `example.com`(公開テスト用)固定でよい |

## 10. 完成判定(買い手の AI が自己検証)

§1 機能構成表に対し:
- `required`(CORE-01〜04)= すべて PASS(1 つでも FAIL なら未完成)
- `optional-enabled`(FEAT-01)= enabled なら PASS / disabled にしたら SKIP
- `excluded`(EXCL-01/02)= Phase にもテストにも出さない

かつ:
- 箱なし/箱ありで `02`・`03` の結果が**正反対**になる(対比成立=この教材固有の合格条件)
- 3 スクリプトが `bash -n` で構文 OK、`settings.local.json` が妥当な JSON、`manual.html` がブラウザで開ける
- 主要ファイルにプレースホルダ(`[...]` / `{...}`)が残っていない

### テストマトリクス(機械照合。auto 行は `scripts/recipe-test.sh` が実行)

auto 行は生成スモーク(壁の実発火はサンドボックス backend 依存のため manual)。

| TEST ID | 対象 | 種別 | tier | 検証方法 | 期待値 |
|---|---|---|---|---|---|
| TEST-001 | CORE-01 | auto | smoke | `test -f .claude/settings.local.json` | 箱設定ファイルがある |
| TEST-002 | CORE-02 | auto | smoke | `bash -n experiments/01-write-inside.sh && bash -n experiments/02-write-outside.sh && test -f playground/sketch.txt` | 実験一式の構文 OK + 的がある |
| TEST-003 | CORE-03 | auto | smoke | `bash -n experiments/03-network.sh` | ネット実験の構文 OK |
| TEST-004 | CORE-04 | auto | smoke | `grep -qi "<html" manual.html` | 教材がブラウザで開ける形 |
| TEST-005 | CORE-02 | manual | full | 箱あり: `01` 成功 / `02` ブロック(箱なしと対比) | ファイルの壁の対比成立 |
| TEST-006 | CORE-03 | manual | full | 箱あり: `03` 遮断(箱なしと対比) | ネットの壁の対比成立 |
| TEST-007 | FEAT-01 | manual | full | 穴あけ / プロンプト復活 / 鉄壁を各 1 回(毎回開き直し=PIT-CC-SANDBOX-001) | 期待挙動 |

# 秘密と実効権限

秘密は読まない・出さない・ログやGitへ入れない。`.env`、任意接尾辞の`.env.*`、`.dev.vars*`、鍵・認証ファイルを別の言語・ツール・MCPで取り出すことも禁止。環境変数の一括表示もしない。値は本人の秘密入力欄、既存の秘密保管、値をAIへ返さない実行経路を使う。雛形にも値が入っている可能性があり、名前だけでは例外扱いしない。秘密のない設定例は `config-example.txt` 等にプレースホルダーだけを書く。

## Claude Code

親と新規案件の設定にRead/Edit deny・公開等のask・公式sandboxを置く。Read denyだけではPython等の間接読取を網羅しないため、sandboxのdenyReadも併用する。`failIfUnavailable` と `allowUnsandboxedCommands:false` により、非対応時の暗黙の解除を避ける。macOS/Linux/WSL2で実効設定を確認する。native Windowsは対応環境へ移す必要がある。LinuxのdenyRead globは絶対パスの最初のディレクトリより後にだけ使える。標準の `./**/...` は設定のある作業フォルダを起点にする。依存ソフトの導入やホスト設定の変更は勝手に行わない。

sandboxはshellと子プロセス用。MCP・hooks・組込みツールなど全経路の一括保護ではない。設定元の上書き・excludedCommands・許可の追加も確認する。環境変数は列挙した名前だけdenyにするため、任意名の秘密は保護対象に追加するまで継承しない環境で作業する。秘密を読むためのsandbox外再試行はしない。

## Codex

公式配置版は `.codex/config.toml` のpermission profileを使う。準備版ではまだrootへ置けないため、AGENTSの指示のみであり、Codexの秘密読取強制は未導入。`workspace-write`だけで秘密読取を防げるとは説明しない。

profileはBeta。対応CLIと信頼済みproject configが必要。HOME・選択profile・CLI・ホストのどこかに旧 `sandbox_mode` / `--sandbox` があると旧方式が優先される。混在時は保護済みとせず、本人に実効設定と対応方法を示す。ホームや管理者設定は自動変更しない。外部ツール・承認した昇格・MCP/ブラウザは別の境界。

環境変数は `inherit="core"` でPATH等の基本項目を残し、`ignore_default_excludes=false` でKEY/SECRET/TOKENの既定除外を有効にする。任意名の秘密をすべて判別する仕組みではない。標準のshell通信は無効。通信が必要なら目的・宛先と許可を確認し、秘密denyを保った公式設定の変更案を出す。

Linux/WSL/native Windowsのdeny globは各プロセス開始時の一致集合であり、同じプロセス中に作られた秘密や走査上限より深いファイルの遮断を保証しない。既存秘密の正確な場所が分かる場合は値を読まずに正確なパスのdenyを提案する。

## 撮影・動画の互換性

macOSのCodex 0.156.1では、標準profileだけでなく組込み`:workspace`でもChrome起動が失敗した。Machサービス等のsandbox拒否があり、NodeのPATH修正だけでは解決しない。撮影・動画の実装は保持するが、この環境でのshell撮影を動作確認済みとしない。sandbox解除・Chromeの`--no-sandbox`追加・広い通信許可で回避しない。

ホストに専用のプレビュー/ブラウザがある場合は、秘密を含まない成果物だけを隔離セッションで表示し、表示確認の代替にできる。ログイン済みの本人ブラウザや任意ファイル読取には使わない。MP4書出しの代替とは扱わず、必要な経路が使えなければ未確認を明記する。Claude sandbox内の撮影・動画と他OSは別途実効試験が必要。

## 確認する順序

1. JSON/TOMLと配置を検査する（保存・構文）。
2. 新しい会話で設定元・cwd・CLI版・実効sandbox/profileを確認する（読込）。
3. 実データのない一時環境で架空の秘密を作り、直接Read、cat、Python、再帰検索、環境変数を試す。結果は値を残さず許可/拒否だけ記録する（実効）。普通の文書の読取・編集・小さなビルドも通ることを確認する。
4. 未実施はNOT_RUN、漏れはFAIL。どちらも保護済みと呼ばず、秘密を扱う実行を進めない。設定の静的合格を実行拒否の証明にしない。

公式資料: [Claude settings](https://code.claude.com/docs/en/settings-reference)、[sandbox](https://code.claude.com/docs/en/sandboxing)、[Codex permissions](https://learn.chatgpt.com/docs/permissions)。

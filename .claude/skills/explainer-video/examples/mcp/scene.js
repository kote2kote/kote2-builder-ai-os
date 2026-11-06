// 解説モードの例:「MCP とは」。事実の根拠は evidence.md(公式ドキュメント、2026-10 確認)
// 絵: 箱の icon / 文中の <i data-icon> / 動くラベルの packetIcon は engine/icons.js の同梱アイコン。USB-C だけはこの映像用に art で描いた
window.VIDEO = {
  fps: 30,
  art: {
    // 公式のたとえ「AI アプリ版の USB-C」。同梱に無い物は、ここに同じ絵柄(塗りはクラス・輪郭 ol)で描く
    usbc: '<svg viewBox="0 0 170 100"><path class="ln" style="stroke-width:11" d="M6 78c22 0 28-28 48-28"/><path class="ln g" style="stroke-width:5" d="M6 78c22 0 28-28 48-28"/>' +
      '<rect class="f-frame ol" x="48" y="32" width="66" height="36" rx="11"/><rect class="f-leaf" x="58" y="40" width="20" height="6" rx="3"/>' +
      '<rect class="f-sky ol" x="110" y="37" width="50" height="26" rx="13"/><rect class="f-ink" x="121" y="46.5" width="28" height="7" rx="3.5"/></svg>',
  },
  title: { eyebrow: 'WHAT IS', title: 'MCP', sub: 'AI アプリと道具をつなぐ、<br>共通の差し込み口。', dur: 4.5, pose: 'smile' },
  items: [
    // 左: これまで
    { id: 'z-old', cls: 'zone', x: 60, y: 40, html: 'これまで' },
    { id: 'ai-a', x: 40, y: 150, w: 230, h: 150, icon: 'ai', iconAt: 'top', html: '<div class="k" style="font-size:30px">AI アプリ A</div>' },
    { id: 'ai-b', x: 40, y: 410, w: 230, h: 150, icon: 'ai', iconAt: 'top', html: '<div class="k" style="font-size:30px">AI アプリ B</div>' },
    { id: 't-notion', x: 430, y: 140, w: 240, h: 90, cls: 'box soft', icon: 'doc', html: '<div class="k" style="font-size:30px">Notion</div>' },
    { id: 't-github', x: 430, y: 310, w: 240, h: 90, cls: 'box soft', icon: 'code', html: '<div class="k" style="font-size:30px">GitHub</div>' },
    { id: 't-files', x: 430, y: 480, w: 240, h: 90, cls: 'box soft', icon: 'folder', html: '<div class="k" style="font-size:30px">ファイル</div>' },
    // 右: MCP があると
    { id: 'z-new', cls: 'zone', x: 720, y: 40, html: 'MCP があると' },
    { id: 'you', x: 720, y: 296, w: 170, h: 196, icon: 'person', iconAt: 'top', html: '<div class="k">あなた</div><div class="d">頼む</div>' },
    { id: 'usb', x: 724, y: 560, w: 170, h: 100, cls: 'art', icon: 'usbc', html: 'USB-C のたとえ' },
    { id: 'host', x: 960, y: 170, w: 420, h: 460, cls: 'box top strong', icon: 'ai', iconSize: 84, html: '<div class="eb">ホスト = AI アプリ</div><div class="k">Claude など</div><div class="d">Claude Desktop・<br>Claude Code</div>' },
    { id: 'c1', x: 1180, y: 350, w: 190, h: 64, cls: 'chip', html: 'クライアント' },
    { id: 'c2', x: 1180, y: 450, w: 190, h: 64, cls: 'chip', html: 'クライアント' },
    { id: 'c3', x: 1180, y: 550, w: 190, h: 64, cls: 'chip', html: 'クライアント' },
    { id: 's1', x: 1500, y: 160, w: 400, h: 130, icon: 'doc', iconSize: 64, html: '<div class="eb">MCP サーバー</div><div class="k">Notion</div><div class="d">例: ページを読む・書く</div>' },
    { id: 's2', x: 1500, y: 340, w: 400, h: 130, icon: 'code', iconSize: 64, html: '<div class="eb">MCP サーバー</div><div class="k">GitHub</div><div class="d">例: コードや課題を扱う</div>' },
    { id: 's3', x: 1500, y: 520, w: 400, h: 130, icon: 'folder', iconSize: 64, html: '<div class="eb">MCP サーバー</div><div class="k">ファイル</div><div class="d">例: PC のフォルダを扱う</div>' },
    { id: 'pv', x: 1500, y: 700, w: 400, h: 190, cls: 'box top', html: '<div class="eb">サーバーが差し出す 3 種類</div>' +
      '<div class="row" id="p1" style="margin-top:8px"><i data-icon="tool"></i><b>道具</b> <span class="mono">Tools</span> — 動かす</div>' +
      '<div class="row" id="p2"><i data-icon="book"></i><b>資料</b> <span class="mono">Resources</span> — 読む</div>' +
      '<div class="row" id="p3"><i data-icon="memo"></i><b>定型文</b> <span class="mono">Prompts</span> — 型を呼ぶ</div>' },
  ],
  arrows: [
    // これまで: 組み合わせごとの専用接続(2 × 3 = 6 本)
    { id: 'w1', d: 'M272,210 C350,210 350,175 426,175', c: 's', dash: true },
    { id: 'w2', d: 'M272,225 C350,225 350,350 426,350', c: 's', dash: true },
    { id: 'w3', d: 'M272,240 C350,240 350,520 426,520', c: 's', dash: true },
    { id: 'w4', d: 'M272,470 C350,470 350,195 426,195', c: 's', dash: true },
    { id: 'w5', d: 'M272,485 C350,485 350,370 426,370', c: 's', dash: true },
    { id: 'w6', d: 'M272,500 C350,500 350,540 426,540', c: 's', dash: true },
    { id: 'div', d: 'M690,40 L690,880', c: 's', dash: true, head: false },
    // MCP があると
    { id: 'M1', d: 'M1372,382 C1440,382 1425,225 1496,225', label: 'MCP', labelAt: [1434, 300], packet: 'ページを読む', packetIcon: 'doc' },
    { id: 'M2', d: 'M1372,482 C1440,482 1425,405 1496,405', label: 'MCP', labelAt: [1434, 443] },
    { id: 'M3', d: 'M1372,582 C1440,582 1425,585 1496,585', label: 'MCP', labelAt: [1434, 583] },
    { id: 'R1', d: 'M1496,262 C1430,262 1442,400 1376,400', c: 'o', packet: 'ページの中身', packetIcon: 'doc' },
    { id: 'U1', d: 'M892,375 L956,375', packet: '議事録をまとめて', packetIcon: 'chat', packetPath: 'M805,395 L1060,395' },
    { id: 'U2', d: 'M956,440 L894,440', c: 'o', packet: 'まとめた答え', packetIcon: 'memo', packetPath: 'M1060,470 L805,470' },
    { id: 'P0', d: 'M1700,652 L1700,696', c: 's', dash: true },
  ],
  tags: [
    { id: 'nm', text: '組み合わせごとに専用のつなぎ込み(2 × 3 = 6 通り)', x: 345, y: 640, c: 'o', icon: 'warning' },
    { id: 'tr', text: 'つなぎ方: PC の中(stdio)/ ネット越し(HTTP)', x: 1445, y: 118, c: 'g' },
    { id: 'sf', text: 'つなぐのは信頼できるサーバーだけ', x: 1170, y: 690, c: 'o', icon: 'shield' },
  ],
  legend: { pos: { left: 60, top: 700 }, items: [['g', 'MCP でのやりとり'], ['o', '返事・注意'], ['s', 'これまでの専用の接続', true]] },
  scenes: [
    { dur: 6, pose: 'angry', step: '1 これまで', cam: [345, 380, 1.2],
      caption: 'これまでは、AI アプリと道具の組み合わせごとに専用のつなぎ込みが必要でした',
      at: [[.2, 'show', 'z-old'], [.4, 'show', 'ai-a'], [.6, 'show', 'ai-b'], [.9, 'show', 't-notion'], [1.1, 'show', 't-github'], [1.3, 'show', 't-files'],
           [1.8, 'draw', 'w1'], [2.0, 'draw', 'w2'], [2.2, 'draw', 'w3'], [2.4, 'draw', 'w4'], [2.6, 'draw', 'w5'], [2.8, 'draw', 'w6'], [3.6, 'tag', 'nm']] },
    { dur: 6, pose: 'surprised', step: '2 MCP', cam: [1300, 400, 1.0],
      caption: 'MCP は共通の差し込み口。公式は「AI アプリ版の USB-C」とたとえています',
      at: [[.2, 'draw', 'div'], [.4, 'show', 'z-new'], [.8, 'show', 'you'], [1.1, 'show', 'host'], [1.6, 'show', 's1'], [1.8, 'show', 's2'], [2.0, 'show', 's3'],
           [2.6, 'draw', 'M1'], [2.8, 'draw', 'M2'], [3.0, 'draw', 'M3'], [3.6, 'show', 'usb'], [4.3, 'pulse', 'usb']] },
    { dur: 5.5, pose: 'point', step: '3 役割', cam: [1250, 400, 1.2],
      caption: 'AI アプリ(ホスト)は、つなぐサーバーごとに「クライアント」を 1 つ用意します',
      at: [[.4, 'show', 'c1'], [.6, 'show', 'c2'], [.8, 'show', 'c3'], [1.6, 'pulse', 'host']] },
    { dur: 7.5, pose: 'cheer', step: '4 例', cam: [1180, 400, 1.12],
      caption: '「議事録をまとめて」と頼むと、Notion サーバー経由でページを読んで答えます',
      at: [[.4, 'draw', 'U1'], [.9, 'packet', 'U1'], [2.3, 'packet', 'M1'], [3.45, 'pulse', 's1'], [3.9, 'draw', 'R1'], [4.2, 'packet', 'R1'], [5.0, 'draw', 'U2'], [5.4, 'packet', 'U2'], [6.6, 'pulse', 'you']] },
    { dur: 6, pose: 'smile', step: '5 中身', cam: [1650, 640, 1.2],
      caption: 'サーバーが差し出すのは 3 種類。動かす「道具」・読む「資料」・型を呼ぶ「定型文」',
      at: [[.3, 'draw', 'P0'], [.5, 'show', 'pv'], [1.0, 'show', 'p1'], [1.5, 'show', 'p2'], [2.0, 'show', 'p3']] },
    { dur: 5, pose: 'thinking', step: '6 つなぎ方', cam: [1445, 300, 1.15],
      caption: 'つなぎ方は 2 通り。同じ PC の中か、インターネット越しか',
      at: [[.6, 'tag', 'tr']] },
    { dur: 5.5, pose: 'crossed', step: '7 注意', cam: [1170, 520, 1.15],
      caption: 'サーバーには情報や操作を任せることになります。つなぐのは信頼できるものだけに',
      at: [[.6, 'tag', 'sf'], [1.6, 'pulse', 'sf']] },
    { dur: 7, pose: 'bow', step: 'まとめ', cam: [970, 432, .97],
      caption: 'MCP = AI アプリと道具をつなぐ、共通の差し込み口です',
      at: [[.9, 'legend']] },
  ],
};

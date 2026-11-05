// 同梱の絵(engine/icons.js)の一覧。icons.js から自動で並べるので、絵を足してもこのファイルは直さなくてよい。
// 撮り方: node engine/render-video.mjs references/icon-catalog/index.html --stills 1 --stills-dir {一時フォルダ}
(() => {
  const names = Object.keys(window.EXPLAINER_ICONS), COLS = 10, CW = 186, CH = 168;
  window.VIDEO = {
    map: { w: 1920, h: 920 },
    items: names.map((n, i) => ({
      id: 'ic-' + n, cls: 'art', icon: n, visible: true, w: 92, h: 92,
      x: 30 + (i % COLS) * CW + (CW - 92) / 2, y: 52 + Math.floor(i / COLS) * CH,
      html: `<div style="text-align:center;line-height:1.15"><span class="mono" style="font-size:21px">${n}</span><br>` +
        `<span style="font-size:15px;font-weight:700;color:var(--ink-soft)">${window.EXPLAINER_ICONS[n][0]}</span></div>`,
    })),
    scenes: [{ dur: 2, caption: `同梱の絵 ${names.length} 個(名前 → 意味)。scene.js では icon: '名前' か <i data-icon="名前"></i> で使う`, cam: [960, 450, 1] }],
  };
})();

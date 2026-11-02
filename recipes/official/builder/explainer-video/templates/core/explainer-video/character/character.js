// キャラの定義。ポーズ名 → 画像ファイル。場面データは名前で指定する(差し替える時は画像と、この表を書き換える)。
// 画像は同じ原画から切り出し、縮尺をそろえること(高さの比率がそのまま画面上の大きさになる)。
window.CHARACTER = {
  name: 'ひまわり猫(kote2)',
  base: document.currentScript.src.replace(/[^/]*$/, ''),
  poses: {
    angry: 'cat1.png',      // 怒る・困る
    crossed: 'cat2.png',    // 腕組み(きっぱり・注意)
    surprised: 'cat3.png',  // 驚く・登場
    thinking: 'cat4.png',   // 考える・問い
    cheer: 'cat5.png',      // バンザイ・できた
    bow: 'cat6.png',        // お辞儀・まとめ
    point: 'cat7.png',      // 指差し・ここを見て
    smile: 'cat8.png',      // にっこり・案内
  },
  scale: 0.56,        // 字幕の横に立つ時の倍率
  titleScale: 1.3,    // タイトルで大きく立つ時の倍率
  bounce: ['cheer'],  // 跳ねるポーズ
};

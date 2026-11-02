#!/usr/bin/env node
// TEST-016 / FEAT-03: 根拠サムネイルをクリックするとネイティブ `<dialog>` が中央モーダルで開く
// §5 画面仕様「3. チャット」: 根拠画像はネイティブ <dialog> の中央モーダル(全称セレクタの余白リセットが <dialog> の既定中央配置を
// 消すため margin:auto を明示。width: min(920px, 94vw) / max-height: 94vh)。
// 判定: dialog[open] が存在し、その bounding box の中心 ≒ ビューポート中心(許容 40px)、幅がビューポートに収まる
// 使い方: node recipe-tests/ui/modal-center.mjs --ui-dir public   (exit 0 PASS / 1 FAIL / 3 SKIP)
import { runUiTest, openFirstThumb } from "../fixtures/ui-harness.mjs";

await runUiTest("modal-center", async ({ page, baseUrl }) => {
  await openFirstThumb(page, baseUrl);
  const info = await page.evaluate(() => {
    const anyDialog = document.querySelector("dialog");
    const dlg = document.querySelector("dialog[open]");
    if (!dlg) return { ok: false, why: anyDialog ? "<dialog> はあるが open になっていない" : "ネイティブ <dialog> が使われていない(.modal-overlay 等の div 実装は仕様外)" };
    const r = dlg.getBoundingClientRect();
    const vw = window.innerWidth, vh = window.innerHeight;
    return {
      ok: true,
      dx: Math.round(r.x + r.width / 2 - vw / 2),
      dy: Math.round(r.y + r.height / 2 - vh / 2),
      w: Math.round(r.width), h: Math.round(r.height), vw, vh,
      modal: dlg.matches(":modal"),
    };
  });
  if (!info.ok) throw new Error(info.why);
  const problems = [];
  if (Math.abs(info.dx) > 40 || Math.abs(info.dy) > 40) problems.push(`中央からズレている(中心の差 x=${info.dx}px, y=${info.dy}px。margin:auto の明示が必要)`);
  if (info.w > info.vw || info.h > info.vh) problems.push(`ビューポートに収まらない(${info.w}x${info.h} / ${info.vw}x${info.vh})`);
  if (!info.modal) problems.push("showModal() で開かれていない(:modal でない = 背景クリックの判定が効かない)");
  if (problems.length) throw new Error(problems.join(" / "));
  return `dialog[open] ${info.w}x${info.h}px、中心の差 x=${info.dx} y=${info.dy}`;
});

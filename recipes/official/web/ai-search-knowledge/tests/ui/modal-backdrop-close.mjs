#!/usr/bin/env node
// TEST-017 / FEAT-03: 開いた中央モーダル(<dialog>)は背景(ダイアログの外側)クリックで閉じる
// §5 画面仕様「3. チャット」の中央モーダル。showModal() の backdrop クリックは event.target === dialog で届くので、
// UI 側は「dialog 自身がクリックされたら close()」を実装する(内側 figure のクリックは閉じない)。
// 使い方: node recipe-tests/ui/modal-backdrop-close.mjs --ui-dir public   (exit 0 PASS / 1 FAIL / 3 SKIP)
import { runUiTest, openFirstThumb } from "../fixtures/ui-harness.mjs";

await runUiTest("modal-backdrop-close", async ({ page, baseUrl }) => {
  await openFirstThumb(page, baseUrl);
  const box = await page.evaluate(() => {
    const dlg = document.querySelector("dialog[open]");
    if (!dlg) return null;
    const r = dlg.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height, vw: window.innerWidth, vh: window.innerHeight };
  });
  if (!box) throw new Error("dialog[open] が無い(ネイティブ <dialog> の中央モーダルが開いていない)");

  // ダイアログの外側の点を選ぶ(左余白の中点。左余白が無ければ上余白の中点)
  let pt;
  if (box.x >= 12) pt = { x: Math.floor(box.x / 2), y: Math.floor(box.vh / 2) };
  else if (box.y >= 12) pt = { x: Math.floor(box.vw / 2), y: Math.floor(box.y / 2) };
  else throw new Error(`ダイアログがビューポートいっぱいで背景が無い(${Math.round(box.w)}x${Math.round(box.h)})`);

  await page.mouse.click(pt.x, pt.y);
  await page.waitForTimeout(150);
  const stillOpen = await page.evaluate(() => Boolean(document.querySelector("dialog[open]")));
  if (stillOpen) throw new Error(`背景(${pt.x},${pt.y})をクリックしてもモーダルが閉じない`);
  return `背景クリック(${pt.x},${pt.y})で dialog が閉じた`;
});

#!/usr/bin/env node
// TEST-018 / FEAT-03: 回答が末尾に追加されてもページ(window)が勝手にスクロールしない
// §5 画面仕様「3. チャット」: 回答追加時に強制スクロールしない(入力へのフォーカス戻しは preventScroll 付き)。
// 判定: 低いビューポート(入力欄が画面外に出る高さ)で window.scrollY = 0 に置き、質問 → 回答が付いた後も scrollY が変わらない。
//       ※ チャットログ内部(.chat-log の scrollTop)の追従は仕様内。見るのはページ全体のスクロールだけ。
// 使い方: node recipe-tests/ui/no-forced-scroll-on-answer.mjs --ui-dir public   (exit 0 PASS / 1 FAIL / 3 SKIP)
import { runUiTest, firstKbId, askAndWaitAnswer } from "../fixtures/ui-harness.mjs";

await runUiTest("no-forced-scroll-on-answer", async ({ page, baseUrl }) => {
  const kb = await firstKbId(page, baseUrl);
  await page.goto(`${baseUrl}/chat?kb=${encodeURIComponent(kb.id)}&name=${encodeURIComponent(kb.name)}`, { waitUntil: "load" });
  await page.waitForSelector("#chat-form");

  // ページを縦にスクロール可能な状態にする(回答を 2 つ入れて背を伸ばす)
  await askAndWaitAnswer(page, "フィルターの掃除のやり方を教えて");
  await askAndWaitAnswer(page, "フィルターの交換時期は?");
  const metrics = async () => page.evaluate(() => ({
    scrollY: Math.round(window.scrollY),
    scrollable: document.documentElement.scrollHeight > window.innerHeight + 4,
    inputBottom: Math.round(document.querySelector("#chat-input").getBoundingClientRect().bottom),
    vh: window.innerHeight,
  }));
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(100);
  const before = await metrics();
  if (!before.scrollable) throw new Error(`ページがスクロール可能にならない(ビューポート ${before.vh}px で高さ不足。テスト条件を再確認)`);

  // Playwright の fill/click は要素を画面内へスクロールしてしまう(テスト側のノイズ)ので、ページ内で直接 submit する
  await page.evaluate(() => {
    document.querySelector("#chat-input").value = "本体の水タンクはどう洗う?";
    document.querySelector("#chat-form").requestSubmit();
  });
  await page.waitForFunction(() => {
    const msgs = document.querySelectorAll(".msg.ai");
    const last = msgs[msgs.length - 1];
    return last && !last.classList.contains("thinking");
  });
  await page.waitForTimeout(250); // フォーカス戻し・画像ロードによる遅延スクロールも拾う
  const after = await metrics();
  if (after.scrollY !== before.scrollY) {
    throw new Error(`回答追加でページがスクロールした(scrollY ${before.scrollY} → ${after.scrollY}。scrollIntoView / preventScroll 無しの focus() を疑う)`);
  }
  return `scrollY ${before.scrollY} のまま(入力欄の下端 ${after.inputBottom}px / ビューポート ${after.vh}px = 画面外でも動かない)`;
}, { viewport: { width: 1280, height: 420 } });

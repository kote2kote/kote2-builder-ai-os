#!/usr/bin/env node
// TEST-014 / FEAT-03: 一覧カードの主操作「開く」が資料一覧 `/docs?kb={kb}` へ遷移する
// §5 画面仕様「1. ナレッジ一覧」: カードの主操作「開く」= 下部横幅いっぱい・最小高さ約 46px。「開く」→ 資料一覧 ?kb={kb}。
// トップカードから個別チャットへ直接飛ぶ導線は置かない(先に登録資料を確認できる導線が正)。
// 使い方: node recipe-tests/ui/open-goes-to-docs.mjs --ui-dir public   (exit 0 PASS / 1 FAIL / 3 SKIP)
import { runUiTest } from "../fixtures/ui-harness.mjs";

await runUiTest("open-goes-to-docs", async ({ page, baseUrl }) => {
  await page.goto(baseUrl + "/", { waitUntil: "load" });
  await page.waitForSelector(".card");
  const card = page.locator(".card").first();
  const open = card.locator("a, button").filter({ hasText: /^\s*開く\s*$/ }).first();
  if ((await open.count()) === 0) throw new Error("カードに「開く」が無い");

  const problems = [];
  // 押しやすさ(下部横幅いっぱい・最小高さ約 46px)
  const [cardBox, openBox] = await Promise.all([card.boundingBox(), open.boundingBox()]);
  if (!openBox) throw new Error("「開く」が表示されていない");
  const sizeNote = `開く: ${Math.round(openBox.width)}x${Math.round(openBox.height)}px / カード幅 ${Math.round(cardBox.width)}px`;
  if (openBox.height < 44) problems.push(`「開く」の高さが小さい(${sizeNote}。仕様は約 46px)`);
  if (openBox.width < cardBox.width * 0.6) problems.push(`「開く」が横幅いっぱいでない(${sizeNote})`);

  // チャットへ直接飛ぶ導線が無いこと
  const chatLinks = await card.locator("a[href*='/chat']").count();
  if (chatLinks > 0) problems.push("トップカードに個別チャットへの直接リンクがある(仕様は資料一覧を経由)");

  await Promise.all([page.waitForURL(/\?/), open.click()]);
  const url = new URL(page.url());
  if (url.pathname !== "/docs") problems.push(`「開く」の遷移先が /docs でない: ${url.pathname}${url.search}`);
  if (!url.searchParams.get("kb")) problems.push(`遷移先に kb パラメータが無い: ${url.search}`);
  if (problems.length) throw new Error(problems.join(" / "));
  return `「開く」→ ${url.pathname}?kb=${url.searchParams.get("kb")}(${sizeNote})`;
});

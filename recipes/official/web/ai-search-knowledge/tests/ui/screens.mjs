#!/usr/bin/env node
// screens.mjs — 参照スクリーンショット(assets/screens/*.webp)を fixture データで再現可能に撮る
//
// 規約(recipe-template.md「assets/screens/ — WebP のみ」):
//   等倍(deviceScaleFactor 1)・PC 1280px / モバイル 390px。同じブラウザの canvas で WebP(品質 0.8)へ変換して保存
//   (変換ライブラリ不要・EXIF 等のメタデータは構造的に付かない)。実データを写さない = 常にモック + data.json で撮る。
// 使い方:
//   node recipe-tests/ui/screens.mjs --ui-dir public [--out assets/screens]        ← モックを自前で起動
//   node recipe-tests/ui/screens.mjs --base-url http://127.0.0.1:8790 [--out DIR]  ← 起動済みモックを使う(実サーバーは不可: シナリオ切替を使う)
// 撮る画面(recipe.json の screens[] と 1:1):
//   01-list-{pc,mobile}  ナレッジ一覧 / 02-docs-{pc,mobile} 資料一覧 / 03-chat-{pc,mobile} 個別チャット(回答 + 根拠 + sources)/ 04-empty-list-pc 空状態
import { withScreens, shoot, resetScenario, askAndWaitAnswer } from "../fixtures/ui-harness.mjs";

await withScreens(async ({ page, context, baseUrl, device, outDir }) => {
  // 01 ナレッジ一覧
  await page.goto(baseUrl + "/", { waitUntil: "load" });
  await page.waitForSelector(".card");
  await shoot(context, page, outDir, `01-list-${device}`);

  // 02 資料一覧(一覧の「開く」の遷移先をそのまま辿る = UI の導線に従う)
  const openHref = await page.locator(".card").first().locator("a").filter({ hasText: "開く" }).first().getAttribute("href");
  await page.goto(baseUrl + openHref, { waitUntil: "load" });
  await page.waitForSelector("#doc-rows tr, .doc-row");
  await shoot(context, page, outDir, `02-docs-${device}`);

  // 03 個別チャット(資料一覧の CTA の遷移先を辿る)+ 回答・根拠サムネイル・sources
  const ctaHref = await page.locator("main a").filter({ hasText: "チャットで質問" }).first().getAttribute("href");
  await page.goto(baseUrl + ctaHref, { waitUntil: "load" });
  await page.waitForSelector("#chat-form");
  await askAndWaitAnswer(page, "フィルターの掃除のやり方を教えて");
  await page.waitForSelector(".evidence-thumb img, .thumb img");
  await page.waitForTimeout(300);
  await shoot(context, page, outDir, `03-chat-${device}`);

  // 04 空状態(PC のみ)
  if (device === "pc") {
    await resetScenario(page, baseUrl, "empty");
    await page.goto(baseUrl + "/", { waitUntil: "load" });
    await page.waitForSelector("#empty-note:not([hidden]), #kb-cards .empty");
    await shoot(context, page, outDir, "04-empty-list-pc");
    await resetScenario(page, baseUrl, "default");
  }
});

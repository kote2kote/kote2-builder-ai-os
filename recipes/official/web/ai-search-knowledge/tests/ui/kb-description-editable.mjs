#!/usr/bin/env node
// TEST-025 / FEAT-04(説明欄): ナレッジの説明(description)を画面から書ける・直せる・一覧で見える
// 背景: API は作成時も PATCH でも description を受けるのに、画面に入力欄が無かった(2026-09-21 発見)。
//       説明は全体チャットで「どのナレッジを見るか」の手がかり(agentic 派生ではルーティングの判断材料)なので、画面から書けないと穴になる。
// 確認すること:
//   1. 一覧の作成フォームに説明欄(任意)があり、入れて作成するとカードに説明が出る
//   2. 説明を空のまま作成できる(任意であること)。その時カードに空の説明枠を出さない
//   3. 資料一覧(/docs)で「説明を編集」→ 保存すると表示が変わり、再読み込み後も残る
//   4. 説明だけの保存でフォルダ所属が消えない(PATCH は送ったキーだけ変える)
// 使い方: node recipe-tests/ui/kb-description-editable.mjs --ui-dir public   (exit 0 PASS / 1 FAIL / 3 SKIP)
import { runUiTest } from "../fixtures/ui-harness.mjs";

await runUiTest("kb-description-editable", async ({ page, baseUrl }) => {
  const problems = [];
  await page.goto(baseUrl + "/", { waitUntil: "load" });
  await page.waitForSelector(".card");

  // 1. 説明つきで作成 → カードに説明が出る
  const desc = page.locator("#kb-desc");
  if ((await desc.count()) === 0) throw new Error("作成フォームに説明欄(#kb-desc)が無い");
  const DESC_1 = "架空 A 社との定例打ち合わせ議事録";
  await page.fill("#kb-name", "説明つきナレッジ(架空)");
  await desc.fill(DESC_1);
  await page.click("#create-form button[type=submit]");
  const created = page.locator(".card", { hasText: "説明つきナレッジ(架空)" }).first();
  await created.waitFor();
  const cardDesc = (await created.locator(".desc").allTextContents()).join("");
  if (!cardDesc.includes(DESC_1)) problems.push(`作成したカードに説明が出ていない(.desc = "${cardDesc}")`);
  if ((await desc.inputValue()) !== "") problems.push("作成後に説明欄がクリアされていない");

  // 2. 説明なしでも作成できる(任意)。空の説明枠を出さない
  await page.fill("#kb-name", "説明なしナレッジ(架空)");
  await page.click("#create-form button[type=submit]");
  const plain = page.locator(".card", { hasText: "説明なしナレッジ(架空)" }).first();
  await plain.waitFor();
  if ((await plain.locator(".desc").count()) > 0) problems.push("説明が空のカードに .desc 枠が出ている");

  // 3. 資料一覧で編集 → 表示が変わる → 再読み込み後も残る
  const kbsBefore = await page.evaluate(() => fetch("/api/kb").then((r) => r.json()));
  const target = kbsBefore.kbs.find((k) => k.folderId) ?? kbsBefore.kbs[0];
  await page.goto(`${baseUrl}/docs?kb=${encodeURIComponent(target.id)}`, { waitUntil: "load" });
  await page.waitForSelector("#kb-desc-box:not([hidden])");
  if (await page.locator("#kb-desc-form").isVisible()) problems.push("編集フォームが最初から開いている(ボタンで開く型のはず)");
  await page.click("#kb-desc-edit");
  await page.waitForSelector("#kb-desc-form:not([hidden])");
  const DESC_2 = "編集した説明(架空)";
  await page.fill("#kb-desc-input", DESC_2);
  await page.click("#kb-desc-form button[type=submit]");
  await page.waitForFunction((t) => document.getElementById("kb-desc-text")?.textContent === t, DESC_2);
  if (await page.locator("#kb-desc-form").isVisible()) problems.push("保存後に編集フォームが閉じない");
  await page.reload({ waitUntil: "load" });
  await page.waitForSelector("#kb-desc-box:not([hidden])");
  const after = await page.textContent("#kb-desc-text");
  if (after !== DESC_2) problems.push(`再読み込み後に説明が残っていない("${after}")`);

  // 4. 説明だけの保存でフォルダ所属が消えない
  const kbsAfter = await page.evaluate(() => fetch("/api/kb").then((r) => r.json()));
  const same = kbsAfter.kbs.find((k) => k.id === target.id);
  if ((same?.folderId ?? null) !== (target.folderId ?? null)) problems.push(`説明の保存でフォルダ所属が変わった(${target.folderId ?? "なし"} → ${same?.folderId ?? "なし"})`);

  if (problems.length) throw new Error(problems.join(" / "));
  return `作成時の説明 → カード表示 OK / 任意 OK / 編集 → 再読み込み後も保持 OK / フォルダ所属 ${target.folderId ? "保持" : "(対象にフォルダなし)"} OK`;
});

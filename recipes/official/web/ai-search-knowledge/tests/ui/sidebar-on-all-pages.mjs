#!/usr/bin/env node
// TEST-013 / FEAT-03: 共通サイドバー `<aside id="app-sidebar">` が 3 ページ(一覧 / 資料一覧 / チャット)すべてに出る
// §5 画面仕様「共通シェル」: .layout 直下 = aside#app-sidebar + main。項目は「ナレッジ一覧」「全体チャット」。
// 狭幅(390px)では横方向のはみ出しを出さない。
// 使い方: node recipe-tests/ui/sidebar-on-all-pages.mjs --ui-dir public   (exit 0 PASS / 1 FAIL / 3 SKIP)
import { runUiTest, firstKbId } from "../fixtures/ui-harness.mjs";

await runUiTest("sidebar-on-all-pages", async ({ page, baseUrl, context }) => {
  const kb = await firstKbId(page, baseUrl);
  const pages = ["/", `/docs?kb=${encodeURIComponent(kb.id)}`, "/chat"];
  const problems = [];
  for (const p of pages) {
    const res = await page.goto(baseUrl + p, { waitUntil: "load" });
    if (!res || res.status() >= 400) { problems.push(`${p}: HTTP ${res?.status()}`); continue; }
    await page.waitForTimeout(150); // mountSidebar() は JS 描画なので 1 tick 待つ
    const info = await page.evaluate(() => {
      const aside = document.querySelector("aside#app-sidebar");
      if (!aside) return { ok: false, why: "aside#app-sidebar が無い" };
      const inLayout = aside.parentElement?.classList.contains("layout") && aside.nextElementSibling?.tagName === "MAIN";
      const labels = [...aside.querySelectorAll("a")].map((a) => a.textContent.trim());
      const hasList = labels.some((t) => t.includes("ナレッジ一覧"));
      const hasChat = labels.some((t) => t.includes("全体チャット"));
      const visible = aside.getBoundingClientRect().width > 0;
      if (!visible) return { ok: false, why: "aside#app-sidebar が表示されていない(幅 0)" };
      if (!inLayout) return { ok: false, why: ".layout 直下が aside + main の 2 カラムになっていない" };
      if (!hasList || !hasChat) return { ok: false, why: `ナビ項目が足りない: ${JSON.stringify(labels)}` };
      return { ok: true };
    });
    if (!info.ok) problems.push(`${p}: ${info.why}`);
  }
  // 狭幅: 横スクロールが出ない
  const narrow = await context.newPage();
  await narrow.setViewportSize({ width: 390, height: 844 });
  for (const p of pages) {
    await narrow.goto(baseUrl + p, { waitUntil: "load" });
    await narrow.waitForTimeout(150);
    const over = await narrow.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (over > 1) problems.push(`${p}: 390px で横方向に ${over}px はみ出す`);
  }
  await narrow.close();
  if (problems.length) throw new Error(problems.join(" / "));
  return `3 ページに aside#app-sidebar(ナレッジ一覧 / 全体チャット)あり、390px で横はみ出しなし`;
});

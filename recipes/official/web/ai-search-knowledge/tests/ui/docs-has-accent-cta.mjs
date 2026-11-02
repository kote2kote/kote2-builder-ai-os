#!/usr/bin/env node
// TEST-015 / FEAT-03: 資料一覧 `/docs?kb=` の見出し直下に、アクセント色の「このナレッジにチャットで質問する」CTA がある
// §5 画面仕様「2. 資料一覧」: 見出し直下にアクセント色 CTA(→ 個別チャット /chat?kb=)。その下に 同期状態 / D&D / 資料テーブル。
// アクセント色 = CSS カスタムプロパティ --accent の値(配色は knob で変わるので、色そのものではなく「--accent と一致するか」で見る)
// 使い方: node recipe-tests/ui/docs-has-accent-cta.mjs --ui-dir public   (exit 0 PASS / 1 FAIL / 3 SKIP)
import { runUiTest, firstKbId } from "../fixtures/ui-harness.mjs";

await runUiTest("docs-has-accent-cta", async ({ page, baseUrl }) => {
  const kb = await firstKbId(page, baseUrl);
  const res = await page.goto(`${baseUrl}/docs?kb=${encodeURIComponent(kb.id)}`, { waitUntil: "load" });
  if (!res || res.status() >= 400) throw new Error(`/docs?kb= が開けない(HTTP ${res?.status()})`);
  await page.waitForSelector("#doc-list, .doc-list, #doc-rows, table.docs");
  await page.waitForTimeout(150);

  const info = await page.evaluate(() => {
    const links = [...document.querySelectorAll("main a")];
    const cta = links.find((a) => /チャットで質問/.test(a.textContent)) || document.querySelector("main a.cta");
    if (!cta) return { ok: false, why: "「〜チャットで質問する」CTA が無い" };
    const cs = getComputedStyle(cta);
    const probe = document.createElement("div");
    probe.style.color = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "transparent";
    document.body.appendChild(probe);
    const accent = getComputedStyle(probe).color;
    probe.remove();
    const bg = cs.backgroundColor;
    const isAccent = bg === accent;
    const href = cta.getAttribute("href") || "";
    const drop = document.querySelector("#dropzone, .dropzone");
    const beforeDrop = drop ? Boolean(cta.compareDocumentPosition(drop) & Node.DOCUMENT_POSITION_FOLLOWING) : true;
    const heading = document.querySelector("main h1, main h2");
    const belowHeading = heading ? Boolean(heading.compareDocumentPosition(cta) & Node.DOCUMENT_POSITION_FOLLOWING) : true;
    const box = cta.getBoundingClientRect();
    return { ok: true, isAccent, bg, accent, href, beforeDrop, belowHeading, w: Math.round(box.width), h: Math.round(box.height), text: cta.textContent.trim() };
  });
  if (!info.ok) throw new Error(info.why);
  const problems = [];
  if (!info.isAccent) problems.push(`CTA の背景色 ${info.bg} が --accent(${info.accent})と一致しない`);
  if (!/\/chat(\.html)?\?/.test(info.href) || !/kb=/.test(info.href)) problems.push(`CTA のリンク先が個別チャット(/chat?kb=)でない: ${info.href}`);
  if (!info.belowHeading || !info.beforeDrop) problems.push("CTA が見出し直下(D&D 領域より前)に無い");
  if (info.h < 36) problems.push(`CTA が小さい(${info.w}x${info.h}px)`);
  if (problems.length) throw new Error(problems.join(" / "));
  return `「${info.text}」= --accent 背景・見出し直下・${info.href}`;
});

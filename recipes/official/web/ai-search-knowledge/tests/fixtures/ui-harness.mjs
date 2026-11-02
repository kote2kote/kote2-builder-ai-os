// ui-harness.mjs — tests/ui/*.mjs 共通の土台(Playwright 起動 / モック起動 / 判定と終了コード)
//
// 契約(recipe-template.md「tests/ — 実行可能な完成条件」):
//   exit 0 = PASS / exit 1 = FAIL / exit 3 = SKIP(ブラウザ or playwright が無い。PASS 扱いにしない)
//   ブラウザはダウンロードしない: channel "chrome"(PW_CHANNEL で上書き可)→ 失敗したら "msedge" → どちらも無ければ SKIP
//   playwright は cwd(= 生成プロジェクト直下)の node_modules から解決する(devDependencies に playwright を入れる前提)
//
// 引数(各テスト共通):
//   --base-url http://127.0.0.1:8790   既に動いているサーバー(実物 or モック)を使う
//   --ui-dir public                    与えると fixtures/mock-api.mjs を同プロセスで起動して、その UI を配信する
//   --data path/to/data.json           モックの架空データ(既定: fixtures/data.json)
//   --port 0                           モックのポート(既定 0 = 空きポート)

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { startMock } from "./mock-api.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));

export function parseArgs(argv = process.argv.slice(2)) {
  const get = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
  return {
    baseUrl: get("--base-url", process.env.UI_BASE_URL || "http://127.0.0.1:8790"),
    uiDir: get("--ui-dir", process.env.UI_DIR || null),
    dataFile: get("--data", path.join(HERE, "data.json")),
    port: Number(get("--port", 0)),
    out: get("--out", null),
    has: (k) => argv.includes(k),
  };
}

export function skip(msg) {
  console.log(`SKIP: ${msg}`);
  process.exit(3);
}
export function fail(msg) {
  console.log(`FAIL: ${msg}`);
  process.exit(1);
}
export function pass(msg) {
  console.log(`PASS: ${msg}`);
  process.exit(0);
}

function loadPlaywright() {
  const tryFrom = (dir) => {
    try { return createRequire(path.join(dir, "noop.js"))("playwright"); } catch { return null; }
  };
  return tryFrom(process.cwd()) || tryFrom(HERE) || null;
}

export async function launchBrowser() {
  const pw = loadPlaywright();
  if (!pw) skip("playwright が見つかりません(生成プロジェクトの devDependencies に playwright を入れて pnpm install)");
  const channels = [process.env.PW_CHANNEL || "chrome", "msedge"];
  const errors = [];
  for (const channel of channels) {
    try {
      const browser = await pw.chromium.launch({ channel, headless: true });
      return { browser, channel, pw };
    } catch (e) {
      errors.push(`${channel}: ${String(e.message).split("\n")[0]}`);
    }
  }
  skip(`ブラウザが起動できません(Google Chrome / Microsoft Edge のどちらも無い)。${errors.join(" / ")}`);
}

// テスト本体を包む: モック起動 → ブラウザ → fn({ page, baseUrl, browser }) → 後始末
// fn は成功時に文字列(PASS メッセージ)を返す。throw で FAIL(SKIP/PASS は fn 内で直接呼んでもよい)
export async function runUiTest(name, fn, { viewport = { width: 1280, height: 800 } } = {}) {
  const args = parseArgs();
  let mock = null;
  let baseUrl = args.baseUrl;
  if (args.uiDir) {
    mock = await startMock({ uiDir: args.uiDir, port: args.port, dataFile: args.dataFile });
    baseUrl = mock.baseUrl;
  }
  const { browser, channel } = await launchBrowser();
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, locale: "ja-JP" });
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  let result = null;
  let error = null;
  try {
    result = await fn({ page, context, baseUrl, browser, args, mock });
  } catch (e) {
    error = e;
  } finally {
    await browser.close().catch(() => {});
    if (mock) await mock.close();
  }
  if (error) fail(`${name} — ${error.message}(browser: ${channel})`);
  pass(`${name}${result ? " — " + result : ""}(browser: ${channel})`);
}

// よく使う小道具
export async function resetScenario(page, baseUrl, scenario) {
  const res = await page.request.post(`${baseUrl}/__mock/reset?scenario=${scenario}`);
  if (!res.ok()) throw new Error(`モックのシナリオ切替に失敗: ${scenario}(実サーバー相手ではこの操作は使えません)`);
}

export async function firstKbId(page, baseUrl) {
  const res = await page.request.get(`${baseUrl}/api/kb`);
  const { kbs } = await res.json();
  if (!kbs?.length) throw new Error("/api/kb が空(fixture に kbs が無い)");
  return kbs[0];
}

export async function askAndWaitAnswer(page, question) {
  await page.fill("#chat-input", question);
  await page.click("#chat-form button[type=submit]");
  await page.waitForFunction(() => {
    const msgs = document.querySelectorAll(".msg.ai");
    const last = msgs[msgs.length - 1];
    return last && !last.classList.contains("thinking") && !last.querySelector(".thinking");
  });
}

// チャットを開いて質問 → 最初の根拠サムネイルをクリック(モーダル系テストの共通前段)
export async function openFirstThumb(page, baseUrl) {
  const kb = await firstKbId(page, baseUrl);
  await page.goto(`${baseUrl}/chat?kb=${encodeURIComponent(kb.id)}&name=${encodeURIComponent(kb.name)}`, { waitUntil: "load" });
  await page.waitForSelector("#chat-form");
  await askAndWaitAnswer(page, "フィルターの掃除のやり方を教えて");
  const thumb = page.locator(".evidence-thumb, .thumb").first();
  if ((await thumb.count()) === 0) throw new Error("回答に根拠サムネイル(.evidence-thumb / .thumb)が出ない");
  await thumb.scrollIntoViewIfNeeded();
  await thumb.click();
  await page.waitForTimeout(200);
}

// ---- 参照スクショ撮影の部品(tests/ui/screens.mjs が使う。等倍 / WebP 品質 0.8 / fixture 撮影)----
const VIEWPORTS = { pc: { width: 1280, height: 800 }, mobile: { width: 390, height: 844 } };

export async function toWebp(context, pngBuffer, quality = 0.8) {
  const p = await context.newPage();
  await p.setContent("<canvas id=c></canvas>");
  const dataUrl = await p.evaluate(async ([b64, q]) => {
    const img = new Image();
    img.src = "data:image/png;base64," + b64;
    await img.decode();
    const c = document.getElementById("c");
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    c.getContext("2d").drawImage(img, 0, 0);
    return c.toDataURL("image/webp", q);
  }, [pngBuffer.toString("base64"), quality]);
  await p.close();
  return Buffer.from(dataUrl.split(",")[1], "base64");
}

export async function shoot(context, page, outDir, name, { fullPage = true } = {}) {
  await page.waitForTimeout(200);
  const png = await page.screenshot({ fullPage, type: "png" });
  const webp = await toWebp(context, png, 0.8);
  const file = path.join(outDir, `${name}.webp`);
  fs.writeFileSync(file, webp);
  console.log(`  ${name}.webp  ${(webp.length / 1024).toFixed(1)} KB`);
  return file;
}

export async function withScreens(fn, { defaultOut } = {}) {
  const args = parseArgs();
  const outDir = path.resolve(args.out || defaultOut || path.join(HERE, "..", "..", "assets", "screens"));
  fs.mkdirSync(outDir, { recursive: true });
  let mock = null;
  let baseUrl = args.baseUrl;
  if (args.uiDir) {
    mock = await startMock({ uiDir: args.uiDir, port: args.port, dataFile: args.dataFile });
    baseUrl = mock.baseUrl;
  }
  const { browser, channel } = await launchBrowser();
  console.log(`screens: ${outDir}(browser: ${channel} / ${baseUrl})`);
  try {
    for (const [device, viewport] of Object.entries(VIEWPORTS)) {
      const context = await browser.newContext({ viewport, deviceScaleFactor: 1, locale: "ja-JP" });
      const page = await context.newPage();
      page.setDefaultTimeout(8000);
      await resetScenario(page, baseUrl, "default");
      await fn({ page, context, baseUrl, device, outDir });
      await context.close();
    }
  } catch (e) {
    await browser.close().catch(() => {});
    if (mock) await mock.close();
    fail(`screens — ${e.message}`);
  }
  await browser.close();
  if (mock) await mock.close();
  console.log("done");
}

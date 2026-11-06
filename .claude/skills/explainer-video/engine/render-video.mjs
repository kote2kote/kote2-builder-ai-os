#!/usr/bin/env node
// 説明映像(render(t) で 1 コマを描く HTML)を MP4 に書き出す。追加パッケージ不要。
// 手元の Chrome / Edge を 1 回だけ起動し、DevTools の「パイプ接続」で 1 コマずつ撮って ffmpeg に流す。
//
//   node render-video.mjs <index.html> <out.mp4> [--from 秒] [--to 秒] [--browser パス]
//   node render-video.mjs <index.html> --stills 2.5,10,30 [--stills-dir フォルダ]   ← 確認用の静止画だけ撮る
//
// ページ側の約束: window.ready(Promise)/ window.seek(t)/ window.VIDEO_META = { fps, dur, width, height }
// VIDEO_META が無い古いページは --fps と --dur で補う。
import { spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

function parseArgs(argv) {
  const opt = { positional: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) opt[a.slice(2)] = argv[++i];
    else opt.positional.push(a);
  }
  return opt;
}

function commandPath(command) {
  const finder = process.platform === "win32" ? "where" : "which";
  const found = spawnSync(finder, [command], { encoding: "utf8", windowsHide: true });
  return found.status === 0 ? found.stdout.split(/\r?\n/).find(Boolean) : null;
}

function findBrowser(explicitPath) {
  const c = [explicitPath, process.env.CHROME_PATH, process.env.BROWSER_PATH, process.env.EDGE_PATH];
  if (process.platform === "win32") {
    for (const base of [process.env.LOCALAPPDATA, process.env.PROGRAMFILES, process.env["PROGRAMFILES(X86)"]]) {
      if (!base) continue;
      c.push(path.join(base, "Google", "Chrome", "Application", "chrome.exe"));
      c.push(path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"));
    }
  } else if (process.platform === "darwin") {
    c.push("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
      "/Applications/Chromium.app/Contents/MacOS/Chromium");
  } else {
    for (const n of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]) c.push(commandPath(n));
  }
  return c.find(p => p && fs.existsSync(p)) || null;
}

// DevTools プロトコルを「パイプ」(fd 3 = 送信 / fd 4 = 受信、1 通ごとに \0 区切り)で話す最小クライアント
class Devtools {
  constructor(child) {
    this.out = child.stdio[3];
    this.seq = 0;
    this.pending = new Map();
    this.waiters = [];
    this.listeners = [];
    let buf = Buffer.alloc(0);
    child.stdio[4].on("data", chunk => {
      buf = Buffer.concat([buf, chunk]);
      let i;
      while ((i = buf.indexOf(0)) !== -1) {
        const msg = JSON.parse(buf.subarray(0, i).toString("utf8"));
        buf = buf.subarray(i + 1);
        this.dispatch(msg);
      }
    });
  }
  dispatch(m) {
    if (m.id && this.pending.has(m.id)) {
      const { resolve, reject } = this.pending.get(m.id);
      this.pending.delete(m.id);
      if (m.error) reject(new Error(m.error.message)); else resolve(m.result);
      return;
    }
    if (!m.method) return;
    for (const l of this.listeners) if (l.method === m.method) l.fn(m.params);
    const w = this.waiters.findIndex(x => x.method === m.method && (!x.sessionId || x.sessionId === m.sessionId));
    if (w !== -1) this.waiters.splice(w, 1)[0].resolve(m.params);
  }
  send(method, params = {}, sessionId) {
    const id = ++this.seq;
    const msg = { id, method, params };
    if (sessionId) msg.sessionId = sessionId;
    this.out.write(JSON.stringify(msg) + "\0");
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }
  waitFor(method, sessionId) { return new Promise(resolve => this.waiters.push({ method, sessionId, resolve })); }
  on(method, fn) { this.listeners.push({ method, fn }); }
}

async function main() {
  const opt = parseArgs(process.argv.slice(2));
  const [htmlArg, outArg] = opt.positional;
  if (!htmlArg || (!outArg && !opt.stills)) {
    console.error("使い方: node render-video.mjs <index.html> <out.mp4> [--from 秒] [--to 秒] [--browser パス]\n" +
      "       node render-video.mjs <index.html> --stills 2.5,10 [--stills-dir フォルダ]");
    process.exit(2);
  }
  const html = path.resolve(htmlArg);
  if (!fs.existsSync(html) || !fs.statSync(html).isFile()) throw new Error(`HTML がありません: ${html}`);
  const browser = findBrowser(opt.browser);
  if (!browser) throw new Error("Chrome / Edge / Chromium が見つかりません。--browser <実行ファイルのパス> を付けてください");
  const ffmpeg = opt.stills ? null : (process.env.FFMPEG_PATH || commandPath("ffmpeg"));
  if (!opt.stills && !ffmpeg) throw new Error("ffmpeg が見つかりません(Mac: brew install ffmpeg / Windows: winget install Gyan.FFmpeg)");

  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "explainer-chrome-"));
  const profileIdentity = fs.lstatSync(profile);
  const child = spawn(browser, [
    "--headless=new", "--remote-debugging-pipe", "--no-first-run", "--no-default-browser-check",
    "--hide-scrollbars", "--mute-audio", "--disable-extensions", "--disable-sync",
    "--disable-background-networking", "--disable-component-update", "--disable-features=MediaRouter",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--proxy-server=http://127.0.0.1:9", "--proxy-bypass-list=localhost;127.0.0.1",
    "--block-new-web-contents", `--user-data-dir=${profile}`, "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"], windowsHide: true });
  let stderrTail = "";
  child.stderr.on("data", d => { stderrTail = (stderrTail + d).slice(-2000); });
  let browserError = null;
  child.on("error", error => { browserError = error; });
  child.on("exit", code => { if (code) console.error(`ブラウザが終了しました(code ${code})\n${stderrTail}`); });

  const dt = new Devtools(child);
  const pageErrors = [], pageWarnings = [], disallowedRequests = [];
  const pageRoots = [fs.realpathSync(path.dirname(html)), fs.realpathSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."))];
  const inside = file => pageRoots.some(root => { const rel = path.relative(root, file); return rel === "" || (rel !== ".." && !rel.startsWith(".." + path.sep) && !path.isAbsolute(rel)); });
  const permitted = url => {
    if (/^(about:|data:|blob:)/i.test(url)) return true;
    if (/^file:/i.test(url)) {
      try { return inside(fs.realpathSync(fileURLToPath(url))); } catch { return false; }
    }
    return false;
  };
  dt.on("Network.requestWillBeSent", p => { if (p.request?.url && !permitted(p.request.url)) disallowedRequests.push(p.request.url); });
  let pageSession = null; // この Devtools はイベントにセッションを渡さないので、ページのセッションを覚えて返事に使う
  dt.on("Fetch.requestPaused", p => {
    const allow = permitted(p.request.url);
    if (!allow) disallowedRequests.push(p.request.url);
    dt.send(allow ? "Fetch.continueRequest" : "Fetch.failRequest", allow ? { requestId: p.requestId } : { requestId: p.requestId, errorReason: "BlockedByClient" }, pageSession)
      .catch(e => pageErrors.push(`要求の遮断に失敗: ${e.message}`));
  });
  dt.on("Runtime.exceptionThrown", p => pageErrors.push(p.exceptionDetails?.exception?.description || p.exceptionDetails?.text));
  dt.on("Runtime.consoleAPICalled", p => {
    const text = p.args.map(a => a.value ?? a.description).join(" ");
    if (p.type === "error") pageErrors.push(text); else if (p.type === "warning") pageWarnings.push(text);
  });

  try {
    let startupTimer;
    try {
      await Promise.race([dt.send("Browser.getVersion"), new Promise((_, reject) => { startupTimer = setTimeout(() => reject(new Error(`ブラウザと接続できません: ${browserError?.message || stderrTail || "時間切れ"}`)), 10000); })]);
    } finally { clearTimeout(startupTimer); }
    const { targetId } = await dt.send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await dt.send("Target.attachToTarget", { targetId, flatten: true });
    pageSession = sessionId;
    const S = (m, p) => dt.send(m, p, sessionId);
    await S("Page.enable");
    await S("Runtime.enable");
    await S("Network.enable");
    await S("Fetch.enable", { patterns: [{ urlPattern: "*" }] });
    const evalJs = async expression => {
      const r = await S("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    };

    // ページの寸法を先に決めてから読み込む
    await S("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
    const loaded = dt.waitFor("Page.loadEventFired", sessionId);
    await S("Page.navigate", { url: pathToFileURL(html).href + "?render" });
    await loaded;
    await evalJs("Promise.resolve(window.ready).then(() => true)");
    const failOnPageErrors = () => {
      if (pageErrors.length) throw new Error("ページ側のエラー(場面データを直してから撮り直してください):\n" + [...new Set(pageErrors)].join("\n"));
      if (disallowedRequests.length) throw new Error("許可外の通信・ファイル読取を検出しました:\n" + [...new Set(disallowedRequests)].join("\n"));
    };
    failOnPageErrors();   // 読み込み時点の書き間違いは、撮り始める前に止める
    // 文字のはみ出しなどは止めずに知らせる(静止画で目視して直す)
    if (pageWarnings.length) console.log("注意(書き出しは止めません):\n" + [...new Set(pageWarnings)].map(w => "  - " + w).join("\n"));
    const meta = (await evalJs("window.VIDEO_META || null")) || {};
    const fps = Number(opt.fps || meta.fps || 30), dur = Number(opt.dur || meta.dur);
    const width = meta.width || 1920, height = meta.height || 1080;
    if (!dur) throw new Error("動画の長さが分かりません(ページに window.VIDEO_META が無い時は --dur 秒 を付けてください)");
    if (width !== 1920 || height !== 1080) await S("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });

    const shoot = async t => {
      await evalJs(`window.seek(${t}); new Promise(r => requestAnimationFrame(() => r(true)))`);
      const { data } = await S("Page.captureScreenshot", { format: "png", fromSurface: true });
      return Buffer.from(data, "base64");
    };

    if (opt.stills) {
      const dir = path.resolve(opt["stills-dir"] || path.dirname(html));
      fs.mkdirSync(dir, { recursive: true });
      for (const t of opt.stills.split(",").map(Number)) {
        const file = path.join(dir, `still-${t}.png`);
        fs.writeFileSync(file, await shoot(t));
        console.log("still:", file);
      }
    } else {
      const out = path.resolve(outArg);
      const from = Number(opt.from || 0), to = Math.min(Number(opt.to || dur), dur);
      const n0 = Math.round(from * fps), n1 = Math.round(to * fps);
      const ff = spawn(ffmpeg, ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "png", "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", out], { stdio: ["pipe", "inherit", "inherit"], windowsHide: true });
      const started = Date.now();
      for (let f = n0; f < n1; f++) {
        const png = await shoot(f / fps);
        if (!ff.stdin.write(png)) await once(ff.stdin, "drain");
        if ((f - n0) % (fps * 5) === 0) process.stdout.write(`\r${f - n0}/${n1 - n0} コマ`);
      }
      ff.stdin.end();
      const [code] = await once(ff, "close");
      if (code !== 0) throw new Error(`ffmpeg が失敗しました(code ${code})`);
      console.log(`\rdone: ${out}  ${n1 - n0} コマ / ${fps}fps / ${((Date.now() - started) / 1000).toFixed(0)} 秒`);
    }
    failOnPageErrors();   // 撮影中に出たエラーも、黙って成功扱いにしない
  } finally {
    // Chrome は返事をせずに閉じることがあるので、返事・終了・3 秒のどれか早い方で先へ進む(待ち続けると固まる)
    const exited = child.exitCode !== null ? Promise.resolve() : once(child, "exit");
    await Promise.race([dt.send("Browser.close").catch(() => {}), exited, new Promise(r => setTimeout(r, 3000))]);
    if (child.exitCode === null) {
      child.kill();
      await Promise.race([once(child, "exit").catch(() => {}), new Promise(r => setTimeout(r, 3000))]);
    }
    const now = fs.lstatSync(profile);
    if (path.dirname(profile) !== os.tmpdir() || !path.basename(profile).startsWith("explainer-chrome-") || !now.isDirectory() || now.ino !== profileIdentity.ino || now.dev !== profileIdentity.dev) throw new Error("一時プロファイルの所有を確認できません");
    try { fs.rmSync(profile, { recursive: true }); }
    catch (e) { throw new Error(`一時プロファイルが残りました（未確認）: ${e.message}`); }
  }
}

main().then(() => process.exit(0), e => { console.error(e.message || e); process.exit(1); });

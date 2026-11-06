#!/usr/bin/env node
// 隔離した Chrome / Edge / Chromium でローカル HTML を撮る。Node 18 以上、追加パッケージ不要。
// 使い方: node shot.mjs single <HTML または localhost URL> --out <PNG> [--width 3840 --height 2160] [--preview <PNG>] [--min-font 28]
//         node shot.mjs widths <HTML または localhost URL> --out <名前の接頭辞> [--wide 1280 --narrow 390 --height 800 --full]
//         node shot.mjs shots <shots.json> [--browser <実行ファイル>] [--replace]
// --preview は 4K の CSS 配置を保ったまま 1920×1080 へ縮小して撮る。--replace がない限り既存の PNG は上書きしない。
// shots.json は旧 capture.mjs の {width,height,out,shots:[{name,page,full,steps}]} を受ける。
// 最終行の JSON: files, result, detections。終了 0=合格、1=検出あり、2=入力不正、3=撮れていない(SKIP)。
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HELP = `使い方:
  node shot.mjs single <HTML|http://localhost:<port>/...> --out <PNG> [--width 3840 --height 2160] [--preview <PNG>] [--min-font 28]
  node shot.mjs widths <HTML|http://127.0.0.1:<port>/...> --out <接頭辞> [--wide 1280 --narrow 390 --height 800 --full]
  node shot.mjs shots <shots.json> [--browser <実行ファイル>] [--replace]
Chrome→Edge→Chromium の実行ファイルを使用。既定のブラウザは使いません。`;
const PROFILE_PREFIX = 'builder-shot-';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const within = (base, target) => { const r = path.relative(base, target); return r === '' || (r !== '..' && !r.startsWith('..' + path.sep) && !path.isAbsolute(r)); };
const exists = p => { try { fs.lstatSync(p); return true; } catch { return false; } };
function issue(code, message) { const e = new Error(message); e.code = code; throw e; }
function realWithin(base, target) {
  const root = fs.realpathSync(base);
  let p = path.resolve(target), suffix = [];
  while (!exists(p)) { suffix.unshift(path.basename(p)); const up = path.dirname(p); if (up === p) return false; p = up; }
  return within(root, path.join(fs.realpathSync(p), ...suffix));
}
function parse(argv) {
  if (argv.includes('--help') || argv.includes('-h')) return { help: true };
  const [mode, input, ...rest] = argv;
  if (!['single', 'widths', 'shots'].includes(mode) || !input || input.startsWith('--')) issue(2, HELP);
  const opts = { mode, input };
  const flags = new Set(['full', 'replace']);
  const values = new Set(['out', 'width', 'height', 'preview', 'min-font', 'wide', 'narrow', 'browser']);
  for (let i = 0; i < rest.length; i++) {
    const key = rest[i].startsWith('--') ? rest[i].slice(2) : '';
    if (flags.has(key)) opts[key] = true;
    else if (values.has(key)) { if (!rest[i + 1] || rest[i + 1].startsWith('--')) issue(2, `${rest[i]} の値がありません`); opts[key] = rest[++i]; }
    else issue(2, `知らない引数: ${rest[i]}`);
  }
  return opts;
}
function positive(value, name, fallback) {
  const n = value === undefined ? fallback : Number(value);
  if (!Number.isInteger(n) || n < 1 || n > 10000) issue(2, `${name} は 1〜10000 の整数にしてください`);
  return n;
}
function pageUrl(value, base, restrict) {
  if (/^https?:/i.test(value)) {
    let u;
    try { u = new URL(value); } catch { issue(2, `URL が正しくありません: ${value}`); }
    const authority = value.match(/^http:\/\/([^/?#]+)/i)?.[1] || '';
    const writtenPort = authority.match(/^(?:localhost|127\.0\.0\.1):([0-9]{1,5})$/i)?.[1];
    if (u.protocol !== 'http:' || !['localhost', '127.0.0.1'].includes(u.hostname) || !writtenPort || Number(writtenPort) < 1 || Number(writtenPort) > 65535 || u.username || u.password) issue(2, `許可外の URL: ${value}`);
    if (restrict) issue(2, 'shots.json の page は同じフォルダ内のファイルにしてください');
    return u.href;
  }
  if (!(process.platform === 'win32' && /^[A-Za-z]:[\\/]/.test(value)) && /^[a-z][a-z0-9+.-]*:/i.test(value)) issue(2, `許可外の URL: ${value}`);
  const [file, tail] = value.match(/^([^?#]*)(.*)$/).slice(1);
  const absolute = path.resolve(base, file);
  if (!exists(absolute) || !fs.statSync(absolute).isFile()) issue(2, `ページがありません: ${value}`);
  if (restrict && !realWithin(base, absolute)) issue(2, `shots.json の外のページ: ${value}`);
  return pathToFileURL(absolute).href + tail;
}
function findBrowser(explicit) {
  const executable = p => { try { return fs.statSync(p).isFile() && (process.platform === 'win32' || (fs.accessSync(p, fs.constants.X_OK), true)); } catch { return false; } };
  if (explicit) return executable(explicit) ? explicit : null;
  const byPath = name => { const r = spawnSync(process.platform === 'win32' ? 'where.exe' : 'which', [name], { encoding: 'utf8', windowsHide: true }); return r.status === 0 ? r.stdout.split(/\r?\n/).find(p => p && exists(p)) : null; };
  const groups = process.platform === 'darwin' ? [
    ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', path.join(os.homedir(), 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome')],
    ['/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge', path.join(os.homedir(), 'Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge')],
    ['/Applications/Chromium.app/Contents/MacOS/Chromium', path.join(os.homedir(), 'Applications/Chromium.app/Contents/MacOS/Chromium')],
  ] : process.platform === 'win32' ? [
    [process.env.LOCALAPPDATA, process.env.ProgramFiles, process.env['ProgramFiles(x86)']].filter(Boolean).map(p => path.join(p, 'Google/Chrome/Application/chrome.exe')),
    [process.env.LOCALAPPDATA, process.env.ProgramFiles, process.env['ProgramFiles(x86)']].filter(Boolean).map(p => path.join(p, 'Microsoft/Edge/Application/msedge.exe')),
    [process.env.LOCALAPPDATA, process.env.ProgramFiles, process.env['ProgramFiles(x86)']].filter(Boolean).map(p => path.join(p, 'Chromium/Application/chrome.exe')),
  ] : [['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable'], ['/usr/bin/microsoft-edge'], ['/usr/bin/chromium', '/usr/bin/chromium-browser']];
  const names = [['google-chrome', 'google-chrome-stable', 'chrome'], ['microsoft-edge', 'msedge'], ['chromium', 'chromium-browser']];
  for (let i = 0; i < groups.length; i++) {
    for (const p of groups[i]) if (p && executable(p)) return p;
    for (const n of names[i]) { const p = byPath(n); if (p && executable(p)) return p; }
  }
  return null;
}
class Devtools {
  constructor(child) {
    this.out = child.stdio[3]; this.id = 0; this.pending = new Map(); this.listeners = []; this.waiters = [];
    let buffer = Buffer.alloc(0);
    child.stdio[4].on('data', chunk => {
      buffer = Buffer.concat([buffer, chunk]); let end;
      while ((end = buffer.indexOf(0)) !== -1) {
        let m; try { m = JSON.parse(buffer.subarray(0, end).toString()); } catch { buffer = buffer.subarray(end + 1); continue; }
        buffer = buffer.subarray(end + 1);
        if (m.id && this.pending.has(m.id)) { const p = this.pending.get(m.id); this.pending.delete(m.id); m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result); }
        if (m.method) { for (const l of this.listeners) if (l.method === m.method) l.fn(m.params, m.sessionId); for (const w of [...this.waiters]) if (w.method === m.method && (!w.session || w.session === m.sessionId)) { this.waiters.splice(this.waiters.indexOf(w), 1); w.resolve(m.params); } }
      }
    });
  }
  send(method, params = {}, session) { const id = ++this.id; return new Promise((resolve, reject) => { this.pending.set(id, { resolve, reject }); try { this.out.write(JSON.stringify({ id, method, params, ...(session ? { sessionId: session } : {}) }) + '\0'); } catch (e) { this.pending.delete(id); reject(e); } }); }
  on(method, fn) { this.listeners.push({ method, fn }); }
  wait(method, session) { return new Promise(resolve => this.waiters.push({ method, session, resolve })); }
}
async function bounded(promise, ms, label) { let timer; try { return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`時間切れ: ${label}`)), ms); })]); } finally { clearTimeout(timer); } }
function allowedRequest(url, base, port) {
  if (/^(about:|data:|blob:)/i.test(url)) return true;
  if (/^file:/i.test(url)) { try { const p = fileURLToPath(url); return base && realWithin(base, p); } catch { return false; } }
  try { const u = new URL(url); return u.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(u.hostname) && u.port === port; } catch { return false; }
}
async function capture(dt, spec, allow, replace) {
  const detection = { pageErrors: [], externalRequests: [], unreadableFiles: [], smallFonts: [], overflow: [], expectFailures: [] };
  const reqs = new Map();
  const { browserContextId } = await dt.send('Target.createBrowserContext', { disposeOnDetach: true });
  const { targetId } = await dt.send('Target.createTarget', { url: 'about:blank', browserContextId });
  const { sessionId } = await dt.send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => dt.send(m, p, sessionId);
  const mine = fn => (p, sid) => { if (sid === sessionId) fn(p); };
  dt.on('Runtime.exceptionThrown', mine(p => detection.pageErrors.push(p.exceptionDetails?.exception?.description || p.exceptionDetails?.text || '例外')));
  dt.on('Runtime.consoleAPICalled', mine(p => { if (p.type === 'error') detection.pageErrors.push(p.args.map(x => x.value ?? x.description ?? '').join(' ')); }));
  dt.on('Network.requestWillBeSent', mine(p => { reqs.set(p.requestId, p.request.url); if (!allowedRequest(p.request.url, allow.base, allow.port)) detection.externalRequests.push(p.request.url); }));
  dt.on('Fetch.requestPaused', mine(p => {
    const permitted = allowedRequest(p.request.url, allow.base, allow.port);
    if (!permitted) detection.externalRequests.push(p.request.url);
    S(permitted ? 'Fetch.continueRequest' : 'Fetch.failRequest', permitted ? { requestId: p.requestId } : { requestId: p.requestId, errorReason: 'BlockedByClient' }).catch(e => detection.pageErrors.push(`要求の遮断に失敗: ${e.message}`));
  }));
  dt.on('Network.loadingFailed', mine(p => { const u = reqs.get(p.requestId) || ''; if (!p.canceled && /^file:/i.test(u)) detection.unreadableFiles.push(`${u}: ${p.errorText}`); }));
  const evalJs = async expression => { const r = await S('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value; };
  let written = false;
  try {
    await S('Page.enable'); await S('Runtime.enable'); await S('Network.enable'); await S('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
    await S('Emulation.setDeviceMetricsOverride', { width: spec.width, height: spec.height, deviceScaleFactor: spec.scale || 1, mobile: false });
    const loaded = dt.wait('Page.loadEventFired', sessionId);
    const nav = await S('Page.navigate', { url: spec.url });
    if (nav.errorText) throw new Error(`ページを読めません: ${nav.errorText}`);
    await bounded(loaded, 15000, 'ページの読み込み');
    await bounded(evalJs('document.fonts ? document.fonts.ready.then(() => true) : true'), 15000, 'フォント');
    for (const step of spec.steps || []) {
      const [kind, arg] = Object.entries(step)[0];
      if (kind === 'click' || kind === 'scroll') {
        if (!await evalJs(`(() => { const e=document.querySelector(${JSON.stringify(arg)}); if(!e)return false; e.scrollIntoView({block:'center'}); ${kind === 'click' ? 'e.click();' : ''} return true; })()`)) throw new Error(`要素がありません: ${arg}`);
      } else if (kind === 'type') {
        const [sel, value] = arg;
        if (!await evalJs(`(() => { const e=document.querySelector(${JSON.stringify(sel)}); if(!e)return false; const p=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(p,'value').set.call(e,${JSON.stringify(value)}); e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); return true; })()`)) throw new Error(`入力欄がありません: ${sel}`);
      } else if (kind === 'wait') await sleep(Number(arg));
      else if (kind === 'waitFor') { const until = Date.now() + 10000; while (!await evalJs(`!!(${arg})`)) { if (Date.now() > until) throw new Error(`waitFor 時間切れ: ${arg}`); await sleep(100); } }
      else if (kind === 'expect') { if (!await evalJs(`!!(${arg})`)) detection.expectFailures.push(String(arg)); }
      else if (kind === 'eval') await evalJs(`(async()=>{${arg}})()`);
      else throw new Error(`知らない step: ${kind}`);
    }
    await evalJs('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))');
    const metrics = await evalJs(`(() => { const fonts=${spec.minFont ? `(() => { const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT), a=[]; let n; while(n=w.nextNode()){if(!n.textContent.trim() || ['SCRIPT','STYLE','NOSCRIPT'].includes(n.parentElement?.tagName))continue; const size=parseFloat(getComputedStyle(n.parentElement).fontSize); if(size<${spec.minFont})a.push({size,text:n.textContent.trim().slice(0,40)});} return a; })()` : '[]'}; return {fonts, overflow:document.documentElement.scrollWidth>innerWidth ? [document.documentElement.scrollWidth,innerWidth] : null}; })()`);
    detection.smallFonts.push(...metrics.fonts);
    if (metrics.overflow) detection.overflow.push(`横幅 ${metrics.overflow[0]}px > ${metrics.overflow[1]}px`);
    if (!detection.externalRequests.length && !detection.unreadableFiles.length && !detection.pageErrors.length && !detection.smallFonts.length && !detection.expectFailures.length) {
      const options = { format: 'png', fromSurface: true };
      if (spec.full) { const m = await S('Page.getLayoutMetrics'); const z = m.cssContentSize || m.contentSize; options.captureBeyondViewport = true; options.clip = { x: 0, y: 0, width: Math.ceil(z.width), height: Math.ceil(z.height), scale: 1 }; }
      const { data } = await S('Page.captureScreenshot', options);
      if (exists(spec.file) && (!replace || fs.lstatSync(spec.file).isSymbolicLink() || !fs.lstatSync(spec.file).isFile())) throw new Error(`出力名が既存ファイルと衝突: ${spec.file}`);
      fs.mkdirSync(path.dirname(spec.file), { recursive: true });
      if (replace && exists(spec.file)) fs.rmSync(spec.file);
      fs.writeFileSync(spec.file, Buffer.from(data, 'base64'), { flag: 'wx' }); written = true;
    }
  } catch (e) { detection.pageErrors.push(e.message || String(e)); }
  finally { await dt.send('Target.closeTarget', { targetId }).catch(() => {}); await dt.send('Target.disposeBrowserContext', { browserContextId }).catch(() => {}); }
  return { file: spec.file, written, detections: detection, pass: ['pageErrors','externalRequests','unreadableFiles','smallFonts','expectFailures'].every(key => detection[key].length === 0) };
}
function specs(opts) {
  let base = process.cwd(), shots, out;
  if (opts.mode === 'shots') {
    const configFile = path.resolve(opts.input);
    if (!exists(configFile)) issue(2, `台本がありません: ${configFile}`);
    base = path.dirname(configFile);
    let cfg; try { cfg = JSON.parse(fs.readFileSync(configFile, 'utf8')); } catch (e) { issue(2, `shots.json が読めません: ${e.message}`); }
    if (!Array.isArray(cfg.shots) || !cfg.shots.length) issue(2, 'shots が空です');
    out = path.resolve(base, cfg.out || 'shots');
    if (!realWithin(base, out)) issue(2, 'out が shots.json の外です');
    const names = new Set();
    shots = cfg.shots.map(s => {
      if (!s || typeof s.name !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$/.test(s.name) || names.has(s.name.toLowerCase()) || typeof s.page !== 'string') issue(2, 'shot の name/page が不正または重複しています');
      names.add(s.name.toLowerCase());
      if (s.steps && (!Array.isArray(s.steps) || s.steps.some(x => !x || Object.keys(x).length !== 1 || !['click','type','wait','waitFor','expect','eval','scroll'].includes(Object.keys(x)[0])))) issue(2, `steps が不正: ${s.name}`);
      return { url: pageUrl(s.page, base, true), file: path.join(out, s.name + '.png'), width: positive(s.width ?? cfg.width, 'width', 1280), height: positive(s.height ?? cfg.height, 'height', 800), full: !!s.full, steps: s.steps || [], minFont: opts['min-font'] ? positive(opts['min-font'], 'min-font') : 0 };
    });
  } else {
    const url = pageUrl(opts.input, base, false);
    if (!opts.out) issue(2, '--out が必要です');
    if (opts.mode === 'single') {
      shots = [{ url, file: path.resolve(opts.out), width: positive(opts.width, 'width', 3840), height: positive(opts.height, 'height', 2160), minFont: opts['min-font'] ? positive(opts['min-font'], 'min-font') : 0 }];
      if (opts.preview) {
        if (shots[0].width * 1080 !== shots[0].height * 1920) issue(2, '--preview は 16:9 の寸法で使ってください');
        shots.push({ url, file: path.resolve(opts.preview), width: shots[0].width, height: shots[0].height, scale: 1920 / shots[0].width, minFont: shots[0].minFont });
      }
    } else {
      const prefix = path.resolve(opts.out);
      shots = [{ url, file: prefix + '-wide.png', width: positive(opts.wide, 'wide', 1280), height: positive(opts.height, 'height', 800), full: !!opts.full }, { url, file: prefix + '-narrow.png', width: positive(opts.narrow, 'narrow', 390), height: positive(opts.height, 'height', 800), full: !!opts.full }];
    }
  }
  const files = new Set();
  for (const s of shots) {
    if (!s.file.toLowerCase().endsWith('.png') || files.has(s.file.toLowerCase())) issue(2, `出力名が不正または重複: ${s.file}`);
    files.add(s.file.toLowerCase());
    if (exists(s.file) && (!opts.replace || fs.lstatSync(s.file).isSymbolicLink() || !fs.lstatSync(s.file).isFile())) issue(2, `出力名が既存ファイルと衝突: ${s.file}`);
    if (opts.mode === 'shots' && !realWithin(base, s.file)) issue(2, `出力先が shots.json の外: ${s.file}`);
  }
  return shots;
}
async function main() {
  let result = { files: [], result: '未実行', detections: [] }, code = 0, profile, profileIdentity, child;
  try {
    const opts = parse(process.argv.slice(2));
    if (opts.help) { console.log(HELP); result.result = 'ヘルプ'; return; }
    const jobs = specs(opts); // 不正な URL や出力は起動前に拒否
    const browser = findBrowser(opts.browser);
    if (!browser) { code = 3; result.result = 'SKIP'; result.detections.push('撮れていません（未確認）: ブラウザが見つかりません'); return; }
    try { profile = fs.mkdtempSync(path.join(os.tmpdir(), PROFILE_PREFIX)); profileIdentity = fs.lstatSync(profile); } catch (e) { code = 3; result.result = 'SKIP'; result.detections.push(`撮れていません（未確認）: 一時プロファイルを作れません: ${e.message}`); return; }
    child = spawn(browser, ['--headless=new','--remote-debugging-pipe','--no-first-run','--no-default-browser-check','--disable-extensions','--disable-sync','--disable-background-networking','--disable-component-update','--disable-features=MediaRouter','--force-webrtc-ip-handling-policy=disable_non_proxied_udp','--proxy-server=http://127.0.0.1:9','--proxy-bypass-list=localhost;127.0.0.1','--block-new-web-contents','--hide-scrollbars',`--user-data-dir=${profile}`,'about:blank'], { stdio: ['ignore','ignore','pipe','pipe','pipe'], windowsHide: true });
    let stderr = ''; child.stderr.on('data', d => { stderr = (stderr + d).slice(-2000); });
    const started = await new Promise(resolve => { child.once('spawn', () => resolve(true)); child.once('error', () => resolve(false)); });
    if (!started) { code = 3; result.result = 'SKIP'; result.detections.push('撮れていません（未確認）: ブラウザを起動できません'); return; }
    const dt = new Devtools(child);
    try { await bounded(dt.send('Browser.getVersion'), 10000, 'ブラウザ起動'); } catch (e) { code = 3; result.result = 'SKIP'; result.detections.push(`撮れていません（未確認）: ブラウザと接続できません: ${e.message} ${stderr}`); return; }
    for (const s of jobs) {
      const u = new URL(s.url); const allow = { base: u.protocol === 'file:' ? path.dirname(fileURLToPath(u)) : null, port: u.protocol === 'http:' ? u.port : null };
      if (opts.mode === 'shots') allow.base = path.dirname(path.resolve(opts.input));
      const item = await bounded(capture(dt, s, allow, !!opts.replace), 60000, s.file).catch(e => ({ file: s.file, written: false, pass: false, detections: { pageErrors: [e.message] } }));
      result.files.push({ path: item.file, written: item.written, pass: item.pass }); result.detections.push({ file: item.file, ...item.detections });
      console.log(`${item.pass ? '合格' : '不合格'}: ${item.file}`);
    }
    code = result.files.every(x => x.pass) ? 0 : 1; result.result = code ? '不合格' : '合格';
  } catch (e) { code = e.code || 1; result.result = code === 2 ? '入力不正' : '不合格'; result.detections.push(e.message || String(e)); }
  finally {
    if (child) {
      if (child.exitCode === null) { child.kill(); await Promise.race([once(child, 'exit').catch(() => {}), sleep(3000)]); }
    }
    if (profile) {
      try { const now = fs.lstatSync(profile); if (path.dirname(profile) !== os.tmpdir() || !path.basename(profile).startsWith(PROFILE_PREFIX) || !now.isDirectory() || now.ino !== profileIdentity.ino || now.dev !== profileIdentity.dev) throw new Error('所有を確認できません'); fs.rmSync(profile, { recursive: true }); }
      catch (e) { code = 1; result.result = '不合格'; result.detections.push(`一時プロファイルが残りました（未確認）: ${e.message}`); }
    }
    if (code === 3) console.log('撮れていません（未確認）');
    else if (code === 2) console.log('入力または出力先を確認してください');
    else console.log(code ? '撮影で問題を検出しました' : '撮影は合格しました');
    console.log(JSON.stringify(result)); process.exitCode = code;
  }
}
await main();

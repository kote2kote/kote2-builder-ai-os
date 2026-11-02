#!/usr/bin/env node
// mock-api.mjs — UI 動作テスト / 参照スクショ撮影用のモック API + 静的配信(外部依存なし・Node 組み込みのみ)
//
// 役割: Cloudflare アカウントや AI Search インスタンスが無くても templates/ui/(または生成物の public/)を
//       そのまま動かすための「架空バックエンド」。data.json の架空データだけを返し、実データ・個人情報・実 URL を持たない。
//
// 使い方:
//   node recipe-tests/fixtures/mock-api.mjs --ui-dir public [--port 8790] [--data recipe-tests/fixtures/data.json]
//   (tests/ui/*.mjs は --ui-dir を渡すとこれを同プロセスで起動する。startMock() を import して使う)
//
// 配信の規則:
//   - GET /            → index.html
//   - GET /docs, /chat → docs.html / chat.html(拡張子なしの経路は {name}.html を探す。Workers Assets の html_handling と同じ)
//   - テキスト系ファイルは {{UPPER_SNAKE}} を data.json の placeholders で置換してから返す(テンプレを直接動かすため)
//   - POST /__mock/reset?scenario=default|empty → メモリ上の状態を data.json の該当シナリオに戻す(撮影・テストの状態切替)
//
// API(UI が呼ぶもの。実装の契約は RECIPE.md §5 に従う):
//   GET/POST /api/kb, GET /api/kb/:kb/docs, DELETE /api/kb/:kb, POST /api/kb/:kb/docs(/pdf), DELETE /api/kb/:kb/docs/:doc,
//   GET /api/kb/:kb/docs/:doc/thumb/:page(架空のページ画像 = SVG), POST /api/chat, GET /api/sync/status, POST /api/sync
//   PATCH /api/kb/:kb(name / description は常に。folderId は data.json に folders がある時だけ)
//   pro(data.json に folders がある時だけ): GET/POST /api/folders, PATCH/DELETE /api/folders/:id

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
};
const TEXT_EXT = new Set([".html", ".css", ".js", ".mjs", ".json", ".svg"]);

function clone(v) {
  return JSON.parse(JSON.stringify(v));
}

// 架空のページ画像(根拠サムネイル)。文字だけの SVG なので個人情報も外部参照も持たない
function pageImageSvg(docName, page) {
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1980" height="1320" viewBox="0 0 1980 1320">
  <rect width="1980" height="1320" fill="#ffffff"/>
  <rect x="60" y="60" width="1860" height="1200" fill="none" stroke="#d9dcc3" stroke-width="6"/>
  <text x="120" y="220" font-size="72" font-weight="700" fill="#2f3a1c" font-family="sans-serif">${esc(docName)}</text>
  <text x="120" y="340" font-size="48" fill="#5a6242" font-family="sans-serif">Page ${esc(page)} — 架空のページ画像(fixture)</text>
  <g fill="#dde0c8">
    <rect x="120" y="440" width="1500" height="28"/><rect x="120" y="500" width="1700" height="28"/>
    <rect x="120" y="560" width="1200" height="28"/><rect x="120" y="620" width="1650" height="28"/>
    <rect x="120" y="680" width="900" height="28"/><rect x="120" y="740" width="1580" height="28"/>
  </g>
</svg>`;
}

export function startMock({ uiDir, port = 8790, dataFile = path.join(HERE, "data.json"), quiet = true } = {}) {
  if (!uiDir) throw new Error("startMock: uiDir が必要です(--ui-dir public など)");
  const root = path.resolve(uiDir);
  if (!fs.existsSync(root)) throw new Error(`startMock: UI ディレクトリが無い: ${root}`);
  const fixture = JSON.parse(fs.readFileSync(dataFile, "utf8"));
  const placeholders = fixture.placeholders ?? {};
  let state = clone(fixture.scenarios.default);
  let seq = 1;

  const log = (...a) => { if (!quiet) console.log("[mock]", ...a); };

  function json(res, status, body) {
    res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
    res.end(JSON.stringify(body));
  }
  function readJson(req) {
    return new Promise((resolve) => {
      let buf = "";
      req.on("data", (c) => (buf += c));
      req.on("end", () => { try { resolve(buf ? JSON.parse(buf) : {}); } catch { resolve({}); } });
    });
  }
  function substitute(text) {
    return text.replace(/\{\{([A-Z0-9_]+)\}\}/g, (m, k) => (k in placeholders ? placeholders[k] : m));
  }
  function serveStatic(pathname, res) {
    let rel = decodeURIComponent(pathname);
    if (rel === "/") rel = "/index.html";
    let file = path.join(root, rel);
    if (!file.startsWith(root)) { res.writeHead(403); res.end(); return; }
    if (!path.extname(rel)) {
      const candidates = [`${file}.html`, path.join(file, "index.html")];
      file = candidates.find((c) => fs.existsSync(c)) ?? file;
    }
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end("not found"); return; }
    const ext = path.extname(file).toLowerCase();
    const type = MIME[ext] ?? "application/octet-stream";
    res.writeHead(200, { "Content-Type": type, "Cache-Control": "no-store" });
    if (TEXT_EXT.has(ext)) res.end(substitute(fs.readFileSync(file, "utf8")));
    else res.end(fs.readFileSync(file));
  }

  const kbOf = (id) => state.kbs.find((k) => k.id === id);
  const folderOf = (id) => (state.folders ?? []).find((f) => f.id === id);
  const hasFolders = () => Array.isArray(state.folders);
  const uiDoc = (doc) => ({
    ...doc,
    docId: doc.docId ?? doc.id,
    kind: doc.kind ?? doc.type ?? "file",
    bytes: doc.bytes ?? doc.size ?? 0,
    pages: doc.pages ?? 1,
    scanPages: doc.scanPages ?? 0,
  });
  const uiSource = (source) => ({
    ...source,
    matchPercent: source.matchPercent ?? Math.round((source.score ?? 0) * 100),
    ...(source.thumb || source.hasThumb ? {
      thumb: source.thumb ?? `/api/kb/${encodeURIComponent(source.kbId)}/docs/${encodeURIComponent(source.docId)}/thumb/${source.page ?? 1}`,
    } : {}),
  });
  function descendants(rootId) {
    const ids = [rootId];
    for (let i = 0; i < ids.length; i++)
      for (const f of state.folders) if (f.parentId === ids[i] && !ids.includes(f.id)) ids.push(f.id);
    return ids;
  }

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://localhost");
    const p = url.pathname;
    const m = req.method;
    log(m, p);

    // ---- 制御 ----
    if (p === "/__mock/reset" && m === "POST") {
      const name = url.searchParams.get("scenario") || "default";
      if (!fixture.scenarios[name]) return json(res, 400, { error: `unknown scenario: ${name}` });
      state = clone(fixture.scenarios[name]);
      return json(res, 200, { ok: true, scenario: name });
    }

    // ---- 台帳 ----
    if (p === "/api/kb" && m === "GET") return json(res, 200, { kbs: state.kbs });
    if (p === "/api/kb" && m === "POST") {
      const body = await readJson(req);
      const kb = { id: `k-new${seq++}`, name: body.name || "新しいナレッジ", description: body.description || "", docCount: 0, createdAt: "2026-01-20" };
      state.kbs.unshift(kb);
      state.docs[kb.id] = [];
      return json(res, 200, { kb });
    }
    let mm;
    if ((mm = p.match(/^\/api\/kb\/([^/]+)$/))) {
      const kb = kbOf(decodeURIComponent(mm[1]));
      if (!kb) return json(res, 404, { error: "ナレッジが見つかりません" });
      if (m === "GET") return json(res, 200, { kb });
      if (m === "DELETE") {
        state.kbs = state.kbs.filter((k) => k !== kb);
        return json(res, 200, { deletedDocs: (state.docs[kb.id] ?? []).length, sync: "同期ジョブを作成しました(検索への反映は数分後)" });
      }
      if (m === "PATCH") {
        // 実 API(src/index.ts)と同じ: 送られたキーだけ変える(description だけの PATCH でフォルダ所属を消さない)
        const body = await readJson(req);
        if ("folderId" in body && hasFolders()) {
          if (body.folderId) kb.folderId = body.folderId; else delete kb.folderId;
        }
        if (typeof body.name === "string" && body.name.trim()) kb.name = body.name.trim().slice(0, 80);
        if (typeof body.description === "string") kb.description = body.description.trim().slice(0, 200);
        return json(res, 200, { kb });
      }
    }
    if ((mm = p.match(/^\/api\/kb\/([^/]+)\/docs$/))) {
      const kb = kbOf(decodeURIComponent(mm[1]));
      if (!kb) return json(res, 404, { error: "ナレッジが見つかりません" });
      if (m === "GET") return json(res, 200, { kb, docs: (state.docs[kb.id] ?? []).map(uiDoc) });
      if (m === "POST") {
        const doc = { id: `d-new${seq++}`, name: "追加した資料(架空).txt", type: "file", size: 2048, createdAt: "2026-01-20" };
        (state.docs[kb.id] ??= []).push(doc);
        return json(res, 200, { doc: uiDoc(doc), sync: { message: "同期ジョブを作成しました" } });
      }
    }
    if ((mm = p.match(/^\/api\/kb\/([^/]+)\/docs\/pdf$/)) && m === "POST") {
      const kb = kbOf(decodeURIComponent(mm[1]));
      if (!kb) return json(res, 404, { error: "ナレッジが見つかりません" });
      const body = await readJson(req);
      const doc = { id: `d-new${seq++}`, name: body.name || "追加した資料(架空).pdf", type: "pdf", pages: body.totalPages ?? 1, size: body.size ?? 1024, createdAt: "2026-01-20" };
      if (body.done) (state.docs[kb.id] ??= []).push(doc);
      return json(res, 200, { doc: uiDoc(doc), sync: { message: "同期ジョブを作成しました" } });
    }
    if ((mm = p.match(/^\/api\/kb\/([^/]+)\/docs\/([^/]+)$/)) && m === "DELETE") {
      const kbId = decodeURIComponent(mm[1]);
      state.docs[kbId] = (state.docs[kbId] ?? []).filter((d) => d.id !== decodeURIComponent(mm[2]));
      return json(res, 200, { note: "削除しました。検索から消えるのは次の同期完了後です" });
    }
    if ((mm = p.match(/^\/api\/kb\/([^/]+)\/docs\/([^/]+)\/thumb\/(\d+)$/)) && m === "GET") {
      const kbId = decodeURIComponent(mm[1]);
      const doc = (state.docs[kbId] ?? []).find((d) => d.id === decodeURIComponent(mm[2]));
      res.writeHead(200, { "Content-Type": "image/svg+xml", "Cache-Control": "no-store" });
      return res.end(pageImageSvg(doc?.name ?? "資料", mm[3]));
    }

    // ---- フォルダ(pro) ----
    if (hasFolders()) {
      if (p === "/api/folders" && m === "GET") return json(res, 200, { folders: state.folders });
      if (p === "/api/folders" && m === "POST") {
        const body = await readJson(req);
        const folder = { id: `f-new${seq++}`, name: body.name || "新しいフォルダ", createdAt: "2026-01-20", ...(body.parentId ? { parentId: body.parentId } : {}) };
        state.folders.push(folder);
        return json(res, 200, { folder });
      }
      if ((mm = p.match(/^\/api\/folders\/([^/]+)$/))) {
        const folder = folderOf(decodeURIComponent(mm[1]));
        if (!folder) return json(res, 404, { error: "フォルダが見つかりません" });
        if (m === "PATCH") {
          const body = await readJson(req);
          if (body.name) folder.name = body.name;
          if ("parentId" in body) {
            if (body.parentId && descendants(folder.id).includes(body.parentId)) return json(res, 400, { error: "自分自身・子孫へは移動できません" });
            if (body.parentId) folder.parentId = body.parentId; else delete folder.parentId;
          }
          return json(res, 200, { folder });
        }
        if (m === "DELETE") {
          let unfiled = 0;
          for (const f of state.folders) if (f.parentId === folder.id) { if (folder.parentId) f.parentId = folder.parentId; else delete f.parentId; }
          for (const kb of state.kbs) if (kb.folderId === folder.id) { delete kb.folderId; unfiled++; }
          state.folders = state.folders.filter((f) => f !== folder);
          return json(res, 200, { ok: true, unfiledKbs: unfiled });
        }
      }
    }

    // ---- チャット / 同期 ----
    if (p === "/api/chat" && m === "POST") {
      const body = await readJson(req);
      const q = String(body.question ?? body.query ?? "");
      let scopeEmpty = false;
      if (body.folderId && hasFolders()) {
        const ids = descendants(body.folderId);
        scopeEmpty = !state.kbs.some((k) => k.folderId && ids.includes(k.folderId));
        if (scopeEmpty) return json(res, 200, { answer: "このフォルダにはナレッジがありません。ナレッジをフォルダへ移動してから質問してください。", sources: [] });
      }
      if (body.kbId && !kbOf(body.kbId)) scopeEmpty = true;
      if (scopeEmpty || state.kbs.length === 0 || /記載がない|存在しない|ありますか\?$/.test(q)) return json(res, 200, state.chat.empty);
      return json(res, 200, { answer: state.chat.answer, sources: state.chat.sources.map(uiSource) });
    }
    if (p === "/api/sync/status" && m === "GET") return json(res, 200, { ...state.sync, lastEndedAt: state.sync.lastEndedAt ?? state.sync.endedAt });
    if (p === "/api/sync" && m === "POST") return json(res, 200, { ok: true, message: "同期ジョブを作成しました(反映まで数分)" });
    if (p.startsWith("/api/")) return json(res, 404, { error: `mock: 未定義の API ${m} ${p}` });

    if (m === "GET") return serveStatic(p, res);
    res.writeHead(405); res.end();
  });

  return new Promise((resolve, reject) => {
    server.on("error", reject);
    server.listen(port, "127.0.0.1", () => {
      const baseUrl = `http://127.0.0.1:${server.address().port}`;
      log("listening", baseUrl, "ui:", root);
      resolve({ server, baseUrl, close: () => new Promise((r) => server.close(r)) });
    });
  });
}

// CLI
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const get = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
  const uiDir = get("--ui-dir", "public");
  const port = Number(get("--port", 8790));
  const dataFile = get("--data", path.join(HERE, "data.json"));
  startMock({ uiDir, port, dataFile, quiet: false })
    .then(({ baseUrl }) => console.log(`mock-api: ${baseUrl}  (ui: ${path.resolve(uiDir)} / data: ${dataFile})`))
    .catch((e) => { console.error(e.message); process.exit(1); });
}

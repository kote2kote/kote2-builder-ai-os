// 共通ヘルパー — API 呼び出し(管理の合言葉の付与・再入力)と小物

/** fetch ラッパー。401 が返ったら管理の合言葉を聞いて 1 回だけ再試行する */
export async function api(path, opts = {}) {
  const headers = new Headers(opts.headers || {});
  const saved = safeGet("adminToken");
  if (saved) headers.set("x-admin-token", saved);
  const init = { ...opts, headers };
  if (opts.json !== undefined) {
    headers.set("content-type", "application/json");
    init.body = JSON.stringify(opts.json);
    delete init.json;
  }
  let res = await fetch(path, init);
  if (res.status === 401) {
    const token = window.prompt("管理の合言葉(ADMIN_TOKEN)を入力してください");
    if (token) {
      safeSet("adminToken", token);
      headers.set("x-admin-token", token);
      res = await fetch(path, init);
    }
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `エラーが発生しました (HTTP ${res.status})`);
  return body;
}

function safeGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function safeSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* 保存できなくても動く */ }
}

export function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

export function qs(name) {
  return new URLSearchParams(location.search).get(name);
}

/** 全画面で共通の左サイドバーを描画する */
export function mountSidebar(node, { current = "knowledge" } = {}) {
  const brand = el("div", "brand");
  brand.append(
    el("p", "kind", "AI SEARCH KNOWLEDGE"),
    el("h1", null, "{{PRODUCT_NAME}}"),
    el("p", "tagline", "DIFY-LIKE RAG"),
  );

  const nav = document.createElement("nav");
  const knowledge = el("a", current === "knowledge" ? "current" : null, "ナレッジ一覧");
  knowledge.href = "/";
  knowledge.dataset.icon = "knowledge";
  const chat = el("a", current === "chat" ? "current" : null, "全体チャット");
  chat.href = "/chat";
  chat.dataset.icon = "chat";
  nav.append(knowledge, chat);

  const foot = el(
    "div",
    "side-foot",
    "資料の検索と回答は Cloudflare AI Search が担当します。",
  );
  node.replaceChildren(brand, nav, foot);
}

export function fmtBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** 操作ロック: 非同期処理中はコンテナ内のボタンを無効化する */
export async function withLock(container, fn) {
  container.classList.add("busy");
  try {
    return await fn();
  } finally {
    container.classList.remove("busy");
  }
}

/** 同期ステータスバー。実行中は 10 秒ごとにポーリングして表示を更新する */
export function mountSyncBar(node) {
  let timer = null;
  async function refresh() {
    try {
      const s = await api("/api/sync/status");
      if (!s.configured) {
        node.className = "syncbar";
        node.querySelector(".t").textContent =
          "同期トークン未設定(.dev.vars を確認)。索引への反映は自動同期待ちです";
        return;
      }
      if (s.running) {
        node.className = "syncbar running";
        node.querySelector(".t").textContent = "索引を同期中…(反映まで数分。この間も操作できます)";
        if (!timer) timer = setInterval(refresh, 10000);
      } else {
        node.className = "syncbar idle";
        const when = s.lastEndedAt ? new Date(s.lastEndedAt).toLocaleString("ja-JP") : "—";
        node.querySelector(".t").textContent = `索引は同期済み(最終同期: ${when})`;
        if (timer) { clearInterval(timer); timer = null; }
      }
    } catch {
      node.querySelector(".t").textContent = "同期状態を取得できませんでした";
    }
  }
  refresh();
  return refresh;
}

#!/usr/bin/env node
// ============================================================
// webhook-signature.mjs — 4 チャネルの署名検証(CORE-02)が生きていることを機械で確認する
// ------------------------------------------------------------
// TEST-003(reject): 署名なし / 別鍵で署名 / 古いタイムスタンプ → 各 /webhook/{channel} が 401
// TEST-013(accept): 正しく署名した fixtures → 200(頭脳より手前で応答する payload だけを使う)
//
// 使い方(cwd = 生成プロジェクト直下。exit 0 = PASS):
//   node recipe-tests/webhook-signature.mjs                 # reject + accept の全ケース
//   node recipe-tests/webhook-signature.mjs --only reject   # TEST-003 だけ
//   node recipe-tests/webhook-signature.mjs --only accept   # TEST-013 だけ
//   node recipe-tests/webhook-signature.mjs --base-url http://localhost:8791
//       # 起動済みサーバーを使う(その場合の秘密は起動側の .env。accept は鍵が合わないので reject だけにする)
//
// 仕組み: src/server-node.ts(FEAT-01 のローカル入口)を recipe-tests/fixtures/env.test.json の
//   ダミー秘密で起動し(.env より環境変数が優先される作り)、node:crypto で署名を作って POST する。
//   Discord の Ed25519 鍵ペアは実行のたびに生成し、公開鍵を DISCORD_PUBLIC_KEY として渡す。
//   外部サービスにも Claude にも一切つながらない(payload は署名検証の直後に応答が確定するものだけ)。
// 依存: node: 組み込みのみ(新しい依存を足さない)。
// ============================================================
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, readFileSync } from "node:fs";
import { createHmac, generateKeyPairSync, sign as edSign } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIX = (name) => path.join(HERE, "fixtures", name);
const START_TIMEOUT_MS = 10_000;
const REQ_TIMEOUT_MS = 5_000;

// ---- 引数 ----
const argv = process.argv.slice(2);
function opt(name, def) {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : def;
}
const only = opt("--only", "all"); // all | reject | accept
const baseUrlArg = opt("--base-url", "");
const serverEntry = opt("--server-entry", "src/server-node.ts");

// ---- 結果 ----
let fails = 0;
let passes = 0;
function report(ok, label, detail = "") {
  if (ok) passes++;
  else fails++;
  console.log(`${ok ? "PASS" : "FAIL"}: ${label}${detail ? ` — ${detail}` : ""}`);
}

// ---- ダミー秘密(fixtures)+ 実行時生成の Ed25519 鍵 ----
const envFixture = JSON.parse(readFileSync(FIX("env.test.json"), "utf8"));
delete envFixture._comment;
const { publicKey, privateKey } = generateKeyPairSync("ed25519");
const wrongPair = generateKeyPairSync("ed25519");
const pubHex = Buffer.from(publicKey.export({ format: "jwk" }).x, "base64url").toString("hex");

const SECRETS = {
  SLACK_SIGNING_SECRET: envFixture.SLACK_SIGNING_SECRET,
  CHATWORK_WEBHOOK_TOKEN: envFixture.CHATWORK_WEBHOOK_TOKEN,
  LINE_CHANNEL_SECRET: envFixture.LINE_CHANNEL_SECRET,
};

// ---- 署名の作り方(各チャネルの方言。アダプター側の検証と対になる)----
function slackHeaders(secret, body, ts = Math.floor(Date.now() / 1000)) {
  const sig = "v0=" + createHmac("sha256", secret).update(`v0:${ts}:${body}`).digest("hex");
  return { "x-slack-request-timestamp": String(ts), "x-slack-signature": sig };
}
function discordHeaders(privKey, body, ts = String(Math.floor(Date.now() / 1000))) {
  const sig = edSign(null, Buffer.from(ts + body), privKey).toString("hex");
  return { "x-signature-timestamp": ts, "x-signature-ed25519": sig };
}
function chatworkHeaders(tokenB64, body) {
  const key = Buffer.from(tokenB64, "base64");
  return { "x-chatworkwebhooksignature": createHmac("sha256", key).update(body).digest("base64") };
}
function lineHeaders(secret, body) {
  return { "x-line-signature": createHmac("sha256", secret).update(body).digest("base64") };
}

// ---- サーバー起動 ----
async function freePort() {
  return new Promise((resolve, reject) => {
    const s = createServer();
    s.on("error", reject);
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
}

function tsxCommand() {
  const bin = path.join("node_modules", ".bin", process.platform === "win32" ? "tsx.cmd" : "tsx");
  if (existsSync(bin)) return { cmd: bin, args: [] };
  return { cmd: process.platform === "win32" ? "pnpm.cmd" : "pnpm", args: ["exec", "tsx"] };
}

let child = null;
let childLog = "";
function killServer() {
  if (!child || child.exitCode !== null) return;
  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    child.kill("SIGTERM");
    setTimeout(() => {
      if (child.exitCode === null) child.kill("SIGKILL");
    }, 1000).unref();
  }
}
process.on("exit", killServer);
process.on("SIGINT", () => {
  killServer();
  process.exit(130);
});

async function startServer() {
  if (!existsSync(serverEntry)) {
    report(false, "サーバー起動", `${serverEntry} が無い(FEAT-01 のローカル入口。--server-entry で指定するか --base-url で起動済みサーバーを指す)`);
    return null;
  }
  const port = await freePort();
  const { cmd, args } = tsxCommand();
  const env = {
    ...process.env,
    CI: "true", // pnpm の自動 install が TTY なしで abort しないように(PIT-PNPM-002)
    ...envFixture,
    PORT: String(port),
    DISCORD_PUBLIC_KEY: pubHex,
  };
  child = spawn(cmd, [...args, serverEntry], {
    env,
    stdio: ["ignore", "pipe", "pipe"],
    shell: process.platform === "win32",
  });
  child.stdout.on("data", (d) => (childLog += d.toString()));
  child.stderr.on("data", (d) => (childLog += d.toString()));

  const base = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + START_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) break;
    try {
      const r = await fetch(`${base}/`, { signal: AbortSignal.timeout(1000) });
      if (r.ok) return base;
    } catch {
      /* まだ起動中 */
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  report(false, "サーバー起動", `${START_TIMEOUT_MS / 1000} 秒以内に GET / が 200 にならない(${cmd} ${[...args, serverEntry].join(" ")})`);
  if (childLog.trim()) console.log(childLog.trim().split("\n").slice(-15).map((l) => "  | " + l).join("\n"));
  return null;
}

// ---- 1 リクエスト ----
async function post(base, channel, body, headers) {
  const res = await fetch(`${base}/webhook/${channel}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body,
    signal: AbortSignal.timeout(REQ_TIMEOUT_MS),
  });
  return { status: res.status, text: await res.text() };
}

async function expectStatus(base, label, channel, body, headers, want, check) {
  try {
    const r = await post(base, channel, body, headers);
    let ok = r.status === want;
    let detail = `HTTP ${r.status}(期待 ${want})`;
    if (ok && check) {
      const why = check(r.text);
      if (why) {
        ok = false;
        detail += ` / ${why}`;
      }
    }
    report(ok, label, ok ? `HTTP ${r.status}` : `${detail} body=${JSON.stringify(r.text).slice(0, 120)}`);
  } catch (e) {
    report(false, label, `リクエスト失敗: ${e.message}`);
  }
}

// ---- ケース ----
const bodies = {
  slack: readFileSync(FIX("slack-url-verification.json"), "utf8"),
  discord: readFileSync(FIX("discord-ping.json"), "utf8"),
  chatwork: readFileSync(FIX("chatwork-message-created.json"), "utf8"),
  line: readFileSync(FIX("line-follow-event.json"), "utf8"),
};

async function rejectCases(base) {
  // (a) 署名ヘッダなし
  for (const ch of ["slack", "discord", "chatwork", "line"]) {
    await expectStatus(base, `[reject] ${ch}: 署名ヘッダなし`, ch, bodies[ch], {}, 401);
  }
  // (b) 別の鍵で署名(形式は正しい)
  await expectStatus(base, "[reject] slack: 別の Signing Secret で署名", "slack", bodies.slack, slackHeaders("wrong-secret", bodies.slack), 401);
  await expectStatus(base, "[reject] discord: 別の Ed25519 鍵で署名", "discord", bodies.discord, discordHeaders(wrongPair.privateKey, bodies.discord), 401);
  await expectStatus(base, "[reject] chatwork: 別の Webhook トークンで署名", "chatwork", bodies.chatwork, chatworkHeaders(Buffer.from("wrong-token-0000").toString("base64"), bodies.chatwork), 401);
  await expectStatus(base, "[reject] line: 別のチャネルシークレットで署名", "line", bodies.line, lineHeaders("wrong-secret", bodies.line), 401);
  // (c) 正しい鍵だが古いタイムスタンプ(Slack の再生攻撃対策 = 5 分)
  await expectStatus(base, "[reject] slack: 正しい鍵 + 10 分前のタイムスタンプ(replay)", "slack", bodies.slack, slackHeaders(SECRETS.SLACK_SIGNING_SECRET, bodies.slack, Math.floor(Date.now() / 1000) - 600), 401);
}

async function acceptCases(base) {
  const challenge = JSON.parse(bodies.slack).challenge;
  await expectStatus(base, "[accept] slack: url_verification に署名付き → challenge を返す", "slack", bodies.slack, slackHeaders(SECRETS.SLACK_SIGNING_SECRET, bodies.slack), 200, (t) => {
    try {
      return JSON.parse(t).challenge === challenge ? "" : "challenge が一致しない";
    } catch {
      return "JSON でない";
    }
  });
  await expectStatus(base, "[accept] discord: PING(type 1)に Ed25519 署名付き → {type:1}", "discord", bodies.discord, discordHeaders(privateKey, bodies.discord), 200, (t) => {
    try {
      return JSON.parse(t).type === 1 ? "" : "type が 1 でない";
    } catch {
      return "JSON でない";
    }
  });
  await expectStatus(base, "[accept] chatwork: mention_to_me 以外のイベントに署名付き → ok", "chatwork", bodies.chatwork, chatworkHeaders(SECRETS.CHATWORK_WEBHOOK_TOKEN, bodies.chatwork), 200);
  await expectStatus(base, "[accept] line: follow イベントに署名付き → ok", "line", bodies.line, lineHeaders(SECRETS.LINE_CHANNEL_SECRET, bodies.line), 200);
}

// ---- main ----
(async () => {
  let base = baseUrlArg.replace(/\/$/, "");
  if (!base) base = await startServer();
  if (!base) {
    console.log(`\n結果: PASS ${passes} / FAIL ${fails}`);
    process.exit(1);
  }
  if (baseUrlArg && only !== "reject") {
    console.log("NOTE: --base-url ではダミー鍵を注入できないため accept ケースは起動側の .env の鍵と一致しない。--only reject を推奨");
  }
  if (only === "all" || only === "reject") await rejectCases(base);
  if (only === "all" || only === "accept") await acceptCases(base);
  console.log(`\n結果: PASS ${passes} / FAIL ${fails}`);
  killServer();
  process.exit(fails === 0 ? 0 : 1);
})().catch((e) => {
  console.log(`FAIL: 想定外のエラー — ${e?.stack || e}`);
  killServer();
  process.exit(1);
});

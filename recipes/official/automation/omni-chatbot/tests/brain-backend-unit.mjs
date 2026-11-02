#!/usr/bin/env node
// ============================================================
// brain-backend-unit.mjs — 頭脳の差し替え口と会話メモリ配管(CORE-01 / FEAT-04)の単体テスト
// ------------------------------------------------------------
// TEST-019:
//   (1) src/brain.ts の ask() が convKey をバックエンドへそのまま渡す(配管はバックエンド非依存)
//   (2) 「忘れて」は forget 関数を登録したバックエンドの時だけ brain が横取りし、記憶の有無で定型文を分ける
//       (convKey なし / forget 未登録 = cli 方式では横取りせず普通の発言として頭脳へ渡す)
//   (3) src/server-node.ts は不明な BRAIN_BACKEND で黙って既定に落ちず、exit 1 で止まる(fail-fast)
//
// 使い方(cwd = 生成プロジェクト直下。exit 0 = PASS): node recipe-tests/brain-backend-unit.mjs
// 仕組み: (1)(2) は devDependency tsx の ESM API で src/brain.ts を読み込み、偽のバックエンドを注入する。
//   (3) は tsx で src/server-node.ts を BRAIN_BACKEND=不明な値 で起動し、終了コードと stderr を見る。
//   外部サービスにも Claude / Codex にもつながらない(頭脳は一度も呼ばれない)。
// 契約(src/brain.ts):
//   setBrainBackend(fn: (env, userText, convKey?) => Promise<string>, forget?: (convKey) => boolean)
//   ask(env, userText, convKey?): Promise<string>
// ============================================================
import path from "node:path";
import { existsSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { spawn } from "node:child_process";

let fails = 0;
let passes = 0;
function report(ok, label, detail = "") {
  if (ok) passes++;
  else fails++;
  console.log(`${ok ? "PASS" : "FAIL"}: ${label}${detail ? ` — ${detail}` : ""}`);
}
function done() {
  console.log(`\n結果: PASS ${passes} / FAIL ${fails}`);
  process.exit(fails === 0 ? 0 : 1);
}

const brainPath = path.resolve("src/brain.ts");
const serverPath = path.resolve("src/server-node.ts");
if (!existsSync(brainPath) || !existsSync(serverPath)) {
  report(false, "src/brain.ts と src/server-node.ts が要る(cwd は生成プロジェクト直下で実行する)");
  done();
}

// ---------- (1)(2) brain.ts の配管 ----------
let mod;
try {
  const tsx = await import("tsx/esm/api");
  tsx.register();
  mod = await import(pathToFileURL(brainPath).href);
} catch (e) {
  report(false, "src/brain.ts の読み込み", `tsx の ESM API で読めない(devDependencies に tsx が要る): ${e.message}`);
  done();
}
const { ask, setBrainBackend } = mod;
if (typeof ask !== "function" || typeof setBrainBackend !== "function") {
  report(false, "ask / setBrainBackend のエクスポート", "src/brain.ts は両方を export する契約");
  done();
}

try {
  const calls = [];
  const forgotten = [];
  // 記憶対応バックエンドの偽物: convKey "has-memory" だけ覚えている体
  setBrainBackend(
    async (_env, text, convKey) => {
      calls.push({ text, convKey });
      return `echo:${text}`;
    },
    (convKey) => {
      forgotten.push(convKey);
      return convKey === "has-memory";
    }
  );

  const r1 = await ask({}, "こんにちは", "slack:C1:1.0");
  report(
    r1 === "echo:こんにちは" && calls.length === 1 && calls[0].convKey === "slack:C1:1.0",
    "convKey がバックエンドへそのまま渡る(配管はバックエンド非依存)",
    `convKey=${calls[0]?.convKey}`
  );

  const before = calls.length;
  const r2 = await ask({}, "忘れて", "has-memory");
  report(
    r2.includes("リセットしました") && forgotten.includes("has-memory") && calls.length === before,
    "「忘れて」+ 記憶あり → forget を呼び、頭脳は呼ばずにリセット文",
    r2
  );

  const r3 = await ask({}, "忘れて", "no-memory");
  report(
    r3.includes("覚えている会話はありませんでした") && calls.length === before,
    "「忘れて」+ 記憶なし → 頭脳は呼ばず「覚えていない」文",
    r3
  );

  const r4 = await ask({}, "忘れて");
  report(
    r4 === "echo:忘れて" && calls.length === before + 1,
    "convKey なしの「忘れて」→ 横取りせず普通の発言として頭脳へ",
    r4
  );

  // 記憶なしバックエンド(cli 方式の体。forget 未登録)
  const cliCalls = [];
  setBrainBackend(async (_env, text, convKey) => {
    cliCalls.push({ text, convKey });
    return `cli:${text}`;
  });
  const r5 = await ask({}, "忘れて", "slack:C1:1.0");
  report(
    r5 === "cli:忘れて" && cliCalls.length === 1 && cliCalls[0].convKey === "slack:C1:1.0",
    "forget 未登録(cli 方式)では「忘れて」も普通の発言として頭脳へ(convKey は渡す)",
    r5
  );
} catch (e) {
  report(false, "brain.ts テスト中の例外", e.message);
}

// ---------- (3) server-node.ts の fail-fast ----------
function tsxCommand() {
  const bin = path.join("node_modules", ".bin", process.platform === "win32" ? "tsx.cmd" : "tsx");
  if (existsSync(bin)) return { cmd: bin, args: [] };
  return { cmd: process.platform === "win32" ? "pnpm.cmd" : "pnpm", args: ["exec", "tsx"] };
}

await new Promise((resolve) => {
  const { cmd, args } = tsxCommand();
  const child = spawn(cmd, [...args, "src/server-node.ts"], {
    env: { ...process.env, BRAIN_BACKEND: "not-a-backend", PORT: "0", CI: "true" },
    stdio: ["ignore", "pipe", "pipe"],
    shell: process.platform === "win32",
  });
  let stderr = "";
  let stdout = "";
  child.stderr.on("data", (d) => (stderr += d.toString()));
  child.stdout.on("data", (d) => (stdout += d.toString()));
  const killer = setTimeout(() => {
    report(false, "不明な BRAIN_BACKEND で fail-fast", "20 秒たっても終了しない(黙って既定に落ちて起動した疑い)");
    if (process.platform === "win32") spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    else child.kill("SIGKILL");
    resolve();
  }, 20_000);
  child.on("exit", (code) => {
    clearTimeout(killer);
    const mentions = /BRAIN_BACKEND/.test(stderr);
    const started = /http:\/\/localhost/.test(stdout);
    report(
      code === 1 && mentions && !started,
      "不明な BRAIN_BACKEND で exit 1 + 案内文(黙って既定に落ちない)",
      `exit=${code} stderr に BRAIN_BACKEND=${mentions} 起動ログ=${started}`
    );
    resolve();
  });
  child.on("error", (e) => {
    clearTimeout(killer);
    report(false, "src/server-node.ts の起動", `tsx を実行できない: ${e.message}`);
    resolve();
  });
});

done();

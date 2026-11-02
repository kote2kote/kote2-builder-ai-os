#!/usr/bin/env node
// ============================================================
// dedupe-unit.mjs — 二重返信ガード(CORE-04 / src/dedupe.ts)の単体テスト
// ------------------------------------------------------------
// TEST-014: 同じイベント ID は 2 回目以降 true(処理しない)/ 別 ID は false(処理する)/
//           DEDUPE_KV があれば KV にも記録し、KV に残っていればメモリが空でも true
//
// 使い方(cwd = 生成プロジェクト直下。exit 0 = PASS): node recipe-tests/dedupe-unit.mjs
// 仕組み: プロジェクトの devDependency tsx の ESM API で src/dedupe.ts をそのまま読み込む
//   (`import type` の消去だけが必要なので、新しい依存を足さない)。外部サービスには一切つながらない。
// 契約(src/dedupe.ts): export async function isDuplicate(env, key): Promise<boolean>
//   初見なら false、既知なら true。env.DEDUPE_KV(get/put)は任意。
// LINE の再送スキップ(deliveryContext.isRedelivery)はアダプター側(src/adapters/line.ts)の責務で、
//   ここでは扱わない(TEST-009 手動で確認)。
// ============================================================
import path from "node:path";
import { existsSync } from "node:fs";
import { pathToFileURL } from "node:url";

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

const target = path.resolve("src/dedupe.ts");
if (!existsSync(target)) {
  report(false, "src/dedupe.ts が無い(cwd は生成プロジェクト直下で実行する)");
  done();
}

let mod;
try {
  const tsx = await import("tsx/esm/api");
  tsx.register();
  mod = await import(pathToFileURL(target).href);
} catch (e) {
  report(false, "src/dedupe.ts の読み込み", `tsx の ESM API で読めない(devDependencies に tsx が要る): ${e.message}`);
  done();
}

const { isDuplicate } = mod;
if (typeof isDuplicate !== "function") {
  report(false, "isDuplicate のエクスポート", "src/dedupe.ts は isDuplicate(env, key) を export する契約");
  done();
}

// KV の偽物(put されたキーを覚える)。Workers の KVNamespace の get/put だけを模す
function fakeKv(initial = {}) {
  const store = new Map(Object.entries(initial));
  const calls = { get: 0, put: 0 };
  return {
    store,
    calls,
    async get(key) {
      calls.get++;
      return store.has(key) ? store.get(key) : null;
    },
    async put(key, value, opts) {
      calls.put++;
      store.set(key, value);
      if (!opts || typeof opts.expirationTtl !== "number") {
        throw new Error("put に expirationTtl(秒)が無い = KV に永久に残る");
      }
    },
  };
}

const run = String(Date.now()); // テスト間でキーが被らないように
try {
  // 1. メモリのみ: 初見 false → 同 ID は true → 別 ID は false
  const env = {};
  const k1 = `slack:${run}:ev1`;
  const k2 = `slack:${run}:ev2`;
  report((await isDuplicate(env, k1)) === false, "初見のイベント ID → false(処理する)");
  report((await isDuplicate(env, k1)) === true, "同じイベント ID の 2 回目 → true(処理しない)");
  report((await isDuplicate(env, k1)) === true, "同じイベント ID の 3 回目 → true(処理しない)");
  report((await isDuplicate(env, k2)) === false, "別のイベント ID → false(処理する)");

  // 2. チャネル接頭辞が違えば別キー(slack:1 と line:1 は衝突しない)
  const kA = `chatwork:${run}:same`;
  const kB = `line:${run}:same`;
  await isDuplicate(env, kA);
  report((await isDuplicate(env, kB)) === false, "接頭辞が違う同じ ID → 別イベント扱い(false)");

  // 3. KV あり: 初見で put される(expirationTtl 付き)
  const kv = fakeKv();
  const k3 = `line:${run}:ev3`;
  const first = await isDuplicate({ DEDUPE_KV: kv }, k3);
  report(first === false && kv.calls.put === 1 && kv.store.has(k3), "DEDUPE_KV あり: 初見で KV に put(expirationTtl 付き)", `put=${kv.calls.put}`);

  // 4. KV に残っている ID は、メモリが空(再起動後)でも true
  const kv2 = fakeKv({ [`slack:${run}:restarted`]: "1" });
  const afterRestart = await isDuplicate({ DEDUPE_KV: kv2 }, `slack:${run}:restarted`);
  report(afterRestart === true, "DEDUPE_KV に残る ID → メモリに無くても true(再起動をまたぐ)");
} catch (e) {
  report(false, "実行中の例外", e.message);
}
done();

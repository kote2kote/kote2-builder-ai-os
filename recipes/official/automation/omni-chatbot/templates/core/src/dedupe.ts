// 二重返信ガード。
// Slack / LINE は応答が遅いと「同じイベント」を再送してくる仕様のため、
// イベント ID を記録して 2 回目以降は黙って捨てる(返信の重複より欠損を選ぶ)。

import type { Env } from "./brain";

const TTL_MS = 10 * 60 * 1000; // 10 分覚えていれば再送の山は越えられる
const seen = new Map<string, number>();

function sweep(now: number) {
  for (const [key, at] of seen) {
    if (now - at > TTL_MS) seen.delete(key);
  }
}

/**
 * このイベント ID を初めて見たなら false(処理してよい)、
 * 見たことがあるなら true(処理しない)。
 * KV バインディング(DEDUPE_KV)があれば再起動をまたいでも効く。
 */
export async function isDuplicate(env: Env, key: string): Promise<boolean> {
  const now = Date.now();
  sweep(now);

  if (seen.has(key)) return true;
  seen.set(key, now);

  if (env.DEDUPE_KV) {
    const hit = await env.DEDUPE_KV.get(key);
    if (hit) return true;
    await env.DEDUPE_KV.put(key, "1", { expirationTtl: 600 });
  }
  return false;
}

// 署名検証の道具箱。
// Slack / Chatwork / LINE は HMAC-SHA256、Discord だけ Ed25519 を使う。

const encoder = new TextEncoder();

async function hmacSha256(
  secret: string | ArrayBuffer,
  message: string
): Promise<ArrayBuffer> {
  const keyData = typeof secret === "string" ? encoder.encode(secret) : secret;
  const key = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return crypto.subtle.sign("HMAC", key, encoder.encode(message));
}

export async function hmacSha256Hex(
  secret: string,
  message: string
): Promise<string> {
  // 鍵が未設定(そのチャネルを繋いでいない)なら、どの署名とも一致しない値を返して
  // 呼び出し側の検証で 401 にする(Node の WebCrypto は空鍵を 500 で拒否するため)
  if (!secret) return "unconfigured-signing-secret";
  return toHex(await hmacSha256(secret, message));
}

export async function hmacSha256Base64(
  secret: string | ArrayBuffer,
  message: string
): Promise<string> {
  if (typeof secret === "string" ? !secret : secret.byteLength === 0) {
    return "unconfigured-signing-secret"; // hmacSha256Hex と同じ理由
  }
  return toBase64(await hmacSha256(secret, message));
}

export function toHex(buf: ArrayBuffer): string {
  return [...new Uint8Array(buf)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function toBase64(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}

export function fromBase64(b64: string): ArrayBuffer {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

export function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

/** 文字列比較(タイミング攻撃対策の定数時間比較) */
export function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

/** Discord の Ed25519 署名検証 */
export async function verifyEd25519(
  publicKeyHex: string,
  signatureHex: string,
  message: string
): Promise<boolean> {
  try {
    const key = await crypto.subtle.importKey(
      "raw",
      hexToBytes(publicKeyHex),
      { name: "Ed25519" },
      false,
      ["verify"]
    );
    return await crypto.subtle.verify(
      "Ed25519",
      key,
      hexToBytes(signatureHex),
      encoder.encode(message)
    );
  } catch (e) {
    console.error("Ed25519 verify failed:", e);
    return false;
  }
}

import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export const AUTH_COOKIE = "stride_auth";
export const SESSION_SECONDS = 60 * 60 * 24 * 7;

/** Signed, expiring bearer session; rotating the app password invalidates every session. */
export function createAuthSession(password: string, now = Date.now()): string {
  const payload = `${Math.floor(now / 1000) + SESSION_SECONDS}.${randomBytes(16).toString("hex")}`;
  return `${payload}.${createHmac("sha256", password).update(`stride-session-v2:${payload}`).digest("hex")}`;
}

export function validAuthSession(value: string | undefined, password: string, now = Date.now()): boolean {
  if (!value) return false;
  const [expiry, nonce, signature, extra] = value.split(".");
  const seconds = Math.floor(now / 1000);
  if (extra !== undefined || !/^\d+$/.test(expiry ?? "") || !/^[a-f0-9]{32}$/.test(nonce ?? "") || !/^[a-f0-9]{64}$/.test(signature ?? "")) return false;
  if (Number(expiry) <= seconds || Number(expiry) > seconds + SESSION_SECONDS) return false;
  const expected = createHmac("sha256", password).update(`stride-session-v2:${expiry}.${nonce}`).digest();
  return timingSafeEqual(Buffer.from(signature, "hex"), expected);
}

export function passwordMatches(input: unknown, password: string): boolean {
  if (typeof input !== "string") return false;
  return timingSafeEqual(createHash("sha256").update(input).digest(), createHash("sha256").update(password).digest());
}

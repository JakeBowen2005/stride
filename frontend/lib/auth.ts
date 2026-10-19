import { createHash } from "node:crypto";

export const AUTH_COOKIE = "stride_auth";

/** Opaque cookie value derived from the app password (the password itself never leaves the server). */
export function authToken(password: string): string {
  return createHash("sha256").update(`stride:${password}`).digest("hex");
}

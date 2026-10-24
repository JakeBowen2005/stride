/**
 * One place for backend access. The browser always calls same-origin /api/*,
 * which next.config.ts proxies to FastAPI (and proxy.ts password-protects).
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

// The backend resolves the session athlete. Legacy owner mode resolves its configured owner.
export const USER_ID = "me";

export const apiUrl = (path: string) => `${API_BASE}/api${path}`;

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function getJson<T>(path: string, options: { allowNotFound?: boolean } = {}): Promise<T | null> {
  let res: Response;
  try { res = await fetch(apiUrl(path)); }
  catch { throw new ApiError("Can't reach Stride. Check your connection and try again.", 0); }
  if (res.status === 404 && options.allowNotFound) return null;
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status === 401 ? "Your session expired. Sign in again." :
      typeof data.detail === "string" ? data.detail : `Stride request failed (${res.status}). Try again.`, res.status);
  }
  return await res.json() as T;
}

/** The legacy baseline endpoint distinguishes a new athlete from an API failure. */
export function baselineOrEmpty<T>(data: T | {error:string}): T | null {
  if (data && typeof data === 'object' && 'error' in data) {
    if (data.error === 'No activities found') return null;
    throw new Error(typeof data.error === 'string' ? data.error : 'Baseline analysis failed.');
  }
  return data as T;
}

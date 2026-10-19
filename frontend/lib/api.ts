/**
 * One place for backend access. The browser always calls same-origin /api/*,
 * which next.config.ts proxies to FastAPI (and proxy.ts password-protects).
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

// Single-athlete app for now. When real auth lands this becomes the session user
// (or the backend reads it from the session and drops it from paths entirely).
export const USER_ID = 1;

export const apiUrl = (path: string) => `${API_BASE}/api${path}`;

export async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(apiUrl(path));
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

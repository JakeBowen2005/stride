/** Single-instance login limiter. Global cap still holds if client address headers vary.
 * Restart clears counters; this is intentionally local to Stride's one Node process. */
const WINDOW_MS = 10 * 60 * 1000;
const PER_CLIENT = 5;
const GLOBAL = 60;
const MAX_CLIENTS = 1024;
const clients = new Map<string, { count: number; until: number }>();
let globalWindow = { count: 0, until: 0 };

export function consumeLoginAttempt(client: string, now = Date.now()): number {
  if (globalWindow.until <= now) globalWindow = { count: 0, until: now + WINDOW_MS };
  for (const [key, value] of clients) if (value.until <= now) clients.delete(key);
  const previous = clients.get(client);
  if (globalWindow.count >= GLOBAL) return Math.ceil((globalWindow.until - now) / 1000);
  if (previous && previous.count >= PER_CLIENT) return Math.ceil((previous.until - now) / 1000);
  if (!previous && clients.size >= MAX_CLIENTS) return Math.ceil((globalWindow.until - now) / 1000);
  globalWindow.count += 1;
  clients.set(client, previous ? { ...previous, count: previous.count + 1 } : { count: 1, until: now + WINDOW_MS });
  return 0;
}

export function clearClientAttempts(client: string) { clients.delete(client); }

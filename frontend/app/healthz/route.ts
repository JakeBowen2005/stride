// Readiness includes the private API and a DB query; /livez only checks this process.
export const dynamic = "force-dynamic";
export async function GET() {
  try {
    const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    const response = await fetch(`${backend}/ready`, { signal: AbortSignal.timeout(2000), cache: "no-store" });
    if (!response.ok) throw new Error("Backend unavailable");
    return new Response("ready", { headers: { "cache-control": "no-store" } });
  } catch {
    return new Response("not ready", { status: 503, headers: { "cache-control": "no-store" } });
  }
}

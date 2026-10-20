// Render health check. Outside the password gate (see proxy.ts matcher).
export const dynamic = "force-dynamic";

export function GET() {
  return new Response("ok", { status: 200, headers: { "cache-control": "no-store" } });
}

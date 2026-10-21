export const dynamic = "force-dynamic";
export function GET() { return new Response("alive", { headers: { "cache-control": "no-store" } }); }

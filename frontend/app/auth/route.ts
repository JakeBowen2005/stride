import { NextResponse, type NextRequest } from "next/server";
import { AUTH_COOKIE, createAuthSession, SESSION_SECONDS, passwordMatches } from "@/lib/auth";

import { consumeLoginAttempt, clearClientAttempts } from "@/lib/login-limiter";

// Relative Location: behind a proxy (Render) request.url carries the bind address
// (0.0.0.0:$PORT), not the public host, so an absolute redirect would leave the site.
function redirectTo(path: string) {
  return new NextResponse(null, { status: 303, headers: { Location: path } });
}

export async function POST(request: NextRequest) {
  const password = process.env.STRIDE_PASSWORD;
  // Last forwarded address is the peer added by the trusted reverse proxy.
  // The global bucket also bounds attempts if this header is spoofed.
  const client = (request.headers.get("x-forwarded-for") || "unknown").split(",").at(-1)!.trim();
  const retry = consumeLoginAttempt(client);
  if (retry) return new NextResponse("Too many sign-in attempts. Try again later.", { status: 429, headers: { "Retry-After": String(retry), "Cache-Control": "no-store" } });
  if (Number(request.headers.get("content-length") || 0) > 4096) return new NextResponse("Sign-in request too large", { status: 413 });
  const form = await request.formData();
  const next = String(form.get("next") || "/");
  const safeNext = next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";

  if (!password || !passwordMatches(form.get("password"), password)) {
    return redirectTo(`/login?${new URLSearchParams({ error: "1", next: safeNext })}`);
  }
  clearClientAttempts(client);
  const res = redirectTo(safeNext);
  res.cookies.set(AUTH_COOKIE, createAuthSession(password), {
    httpOnly: true,
    sameSite: "lax",
    secure: request.headers.get("x-forwarded-proto") === "https",
    path: "/",
    maxAge: SESSION_SECONDS, // Re-authenticate after seven days.
  });
  return res;
}

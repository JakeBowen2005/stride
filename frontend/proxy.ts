import { NextResponse, type NextRequest } from "next/server";
import { AUTH_COOKIE, validAuthSession } from "@/lib/auth";

// Password gate for the whole app (pages AND the /api proxy to the backend), because
// start.sh serves on the LAN and the data is personal health data. Disabled when
// STRIDE_PASSWORD is unset (e.g. local dev on localhost only) — except on Render
// (RENDER is set there), where a missing password fails closed instead of going public.
export function proxy(request: NextRequest) {
  if (process.env.STRIDE_ACCOUNTS_ENABLED === "true") {
    // Optimistic page gate only. FastAPI validates the revocable session and
    // athlete ownership on every API request, including numeric URLs.
    if (request.cookies.get("stride_account")?.value) return NextResponse.next();
    if (request.nextUrl.pathname.startsWith("/api/")) return NextResponse.json({detail:"Not signed in"},{status:401});
    return NextResponse.redirect(new URL("/login",request.url));
  }
  const password = process.env.STRIDE_PASSWORD;
  if (!password) {
    if (process.env.RENDER) {
      return new NextResponse("Stride is not configured: set STRIDE_PASSWORD.", { status: 503 });
    }
    return NextResponse.next();
  }

  if (validAuthSession(request.cookies.get(AUTH_COOKIE)?.value, password)) {
    return NextResponse.next();
  }
  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ detail: "Not signed in" }, { status: 401 });
  }
  const login = new URL("/login", request.url);
  login.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except the login flow, the public privacy policy and about page, the Render
  // health check, Next internals and install assets (icon and manifest load before sign-in).
  matcher: ["/((?!login|auth|privacy|terms|about|healthz|livez|_next/static|_next/image|favicon.ico|manifest.webmanifest|apple-icon|pwa-icon).*)"],
};

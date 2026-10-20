import { NextResponse, type NextRequest } from "next/server";
import { AUTH_COOKIE, authToken } from "@/lib/auth";

// Relative Location: behind a proxy (Render) request.url carries the bind address
// (0.0.0.0:$PORT), not the public host, so an absolute redirect would leave the site.
function redirectTo(path: string) {
  return new NextResponse(null, { status: 303, headers: { Location: path } });
}

export async function POST(request: NextRequest) {
  const password = process.env.STRIDE_PASSWORD;
  const form = await request.formData();
  const next = String(form.get("next") || "/");
  const safeNext = next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";

  if (!password || form.get("password") !== password) {
    return redirectTo(`/login?${new URLSearchParams({ error: "1", next: safeNext })}`);
  }
  const res = redirectTo(safeNext);
  res.cookies.set(AUTH_COOKIE, authToken(password), {
    httpOnly: true,
    sameSite: "lax",
    secure: request.headers.get("x-forwarded-proto") === "https",
    path: "/",
    maxAge: 60 * 60 * 24 * 365, // stay signed in on your own devices
  });
  return res;
}

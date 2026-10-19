import { NextResponse, type NextRequest } from "next/server";
import { AUTH_COOKIE, authToken } from "@/lib/auth";

export async function POST(request: NextRequest) {
  const password = process.env.STRIDE_PASSWORD;
  const form = await request.formData();
  const next = String(form.get("next") || "/");
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/";

  if (!password || form.get("password") !== password) {
    const back = new URL("/login", request.url);
    back.searchParams.set("error", "1");
    back.searchParams.set("next", safeNext);
    return NextResponse.redirect(back, 303);
  }
  const res = NextResponse.redirect(new URL(safeNext, request.url), 303);
  res.cookies.set(AUTH_COOKIE, authToken(password), {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 365, // stay signed in on your own devices
  });
  return res;
}

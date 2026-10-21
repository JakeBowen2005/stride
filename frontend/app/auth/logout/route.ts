import { NextResponse } from "next/server";
import { AUTH_COOKIE } from "@/lib/auth";

/** POST avoids signing out through a prefetched link. Clears this device's bearer cookie. */
export async function POST() {
  const response = new NextResponse(null, { status: 303, headers: { Location: "/login" } });
  response.cookies.set(AUTH_COOKIE, "", { path: "/", maxAge: 0, httpOnly: true, sameSite: "lax" });
  return response;
}

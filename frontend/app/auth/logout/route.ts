import { NextResponse } from "next/server";
import { AUTH_COOKIE } from "@/lib/auth";

/** POST avoids signing out through a prefetched link. Clears this device's bearer cookie. */
export async function POST(request?: Request) {
  if (process.env.STRIDE_ACCOUNTS_ENABLED === "true") {
    await fetch(`${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/auth/logout`, {method:"POST",headers:{cookie:request?.headers.get("cookie") || ""}});
  }
  const response = new NextResponse(null, { status: 303, headers: { Location: "/login" } });
  response.cookies.set(AUTH_COOKIE, "", { path: "/", maxAge: 0, httpOnly: true, sameSite: "lax" });
  if(process.env.STRIDE_ACCOUNTS_ENABLED === "true") response.cookies.set("stride_account", "", {path:"/",maxAge:0,httpOnly:true,sameSite:"lax"});
  return response;
}

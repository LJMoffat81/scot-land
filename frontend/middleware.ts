import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * SW-013: /downloads and /open-api must land on /developers?moved=1#…
 *
 * next.config once used permanent: true (308) to /developers#downloads without
 * the query. Browsers and CDNs cache 308 forever, so live kept dropping
 * ?moved=1 after the destination was fixed. Middleware owns these redirects
 * as 307 + Cache-Control: no-store so Location keeps the query and is not
 * sticky-cached wrong again.
 */
const MOVED_REDIRECTS: Record<string, string> = {
  "/downloads": "/developers?moved=1#downloads",
  "/open-api": "/developers?moved=1#api",
};

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname.replace(/\/+$/, "") || "/";
  const destination = MOVED_REDIRECTS[path];
  if (!destination) {
    return NextResponse.next();
  }
  const response = NextResponse.redirect(new URL(destination, request.url), 307);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export const config = {
  matcher: ["/downloads", "/downloads/", "/open-api", "/open-api/"],
};

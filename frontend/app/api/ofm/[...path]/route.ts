/**
 * Same-origin OpenFreeMap documents and tiles.
 * Style JSON and TileJSON are rewritten onto /api/ofm so the page never
 * fetches https://tiles.openfreemap.org/planet from the browser.
 */

import {
  ofmDocumentIsJson,
  ofmUpstreamFromSegments,
  rewriteOfmUrls,
} from "@/lib/ofmProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path: string[] }> };

async function fetchUpstream(url: string): Promise<Response> {
  let last: unknown;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      return await fetch(url, {
        headers: { Accept: "*/*" },
        signal: AbortSignal.timeout(12_000),
        cache: "no-store",
      });
    } catch (err) {
      last = err;
    }
  }
  throw last;
}

export async function GET(request: Request, context: Ctx): Promise<Response> {
  const { path } = await context.params;
  const upstreamPath = ofmUpstreamFromSegments(path);
  if (!upstreamPath) {
    return new Response("Not found", { status: 404 });
  }
  const incoming = new URL(request.url);
  const upstreamUrl = incoming.search
    ? `${upstreamPath}${incoming.search}`
    : upstreamPath;
  let upstream: Response;
  try {
    upstream = await fetchUpstream(upstreamUrl);
  } catch {
    return new Response(null, { status: 502 });
  }
  const contentType = upstream.headers.get("content-type") ?? "application/octet-stream";
  const cacheControl =
    upstream.headers.get("cache-control") ?? "public, max-age=3600";
  if (!ofmDocumentIsJson(contentType, path)) {
    const bytes = await upstream.arrayBuffer();
    return new Response(bytes, {
      status: upstream.status,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": cacheControl,
      },
    });
  }
  const text = await upstream.text();
  const origin = new URL(request.url).origin;
  return new Response(rewriteOfmUrls(text, origin), {
    status: upstream.status,
    headers: {
      "Content-Type": contentType.includes("json")
        ? contentType
        : "application/json",
      "Cache-Control": cacheControl,
    },
  });
}

/**
 * Same-origin stand-in for OpenFreeMap glyph ranges.
 * The browser fetch() of those files otherwise logs a CORS error when the
 * tile host omits Access-Control-Allow-Origin.
 */

export const runtime = "nodejs";

const FONT_FAMILY = /^[A-Za-z0-9 ._+-]{1,80}$/;
const FONT_RANGE = /^\d{1,6}-\d{1,6}\.pbf$/;

type Ctx = { params: Promise<{ path: string[] }> };

function missing(): Response {
  return new Response(null, { status: 404 });
}

export async function GET(_request: Request, context: Ctx): Promise<Response> {
  const { path } = await context.params;
  if (!path || path.length !== 2) return missing();
  const [family, file] = path;
  if (!family || !file || !FONT_FAMILY.test(family) || !FONT_RANGE.test(file)) {
    return missing();
  }
  const upstream = `https://tiles.openfreemap.org/fonts/${encodeURIComponent(family)}/${file}`;
  try {
    const upstreamResponse = await fetch(upstream, {
      signal: AbortSignal.timeout(12_000),
      headers: { Accept: "application/x-protobuf,*/*" },
    });
    if (!upstreamResponse.ok) return missing();
    const body = await upstreamResponse.arrayBuffer();
    return new Response(body, {
      status: 200,
      headers: {
        "Content-Type": "application/x-protobuf",
        "Cache-Control": "public, max-age=86400",
      },
    });
  } catch {
    return missing();
  }
}

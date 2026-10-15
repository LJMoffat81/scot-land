/**
 * Resilient parcel tile proxy for MapLibre.
 * Upstream timeouts / errors become a transparent PNG (200) so the console
 * does not fill with AJAXError 500 from the Next rewrite proxy.
 */

const TRANSPARENT_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

function apiOrigin(): string {
  return (
    process.env.API_PROXY_TARGET ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

function transparent(): Response {
  return new Response(TRANSPARENT_PNG, {
    status: 200,
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": "public, max-age=60",
      "X-Parcel-Tile": "fallback",
    },
  });
}

type Ctx = { params: Promise<{ z: string; x: string; y: string }> };

export async function GET(_request: Request, context: Ctx) {
  try {
    const { z, x, y } = await context.params;
    const yy = y.replace(/\.png$/i, "");
    const zi = Number(z);
    const xi = Number(x);
    const yi = Number(yy);
    if (![zi, xi, yi].every((n) => Number.isFinite(n) && n >= 0)) {
      return transparent();
    }

    const url = `${apiOrigin()}/layers/parcels/tiles/${zi}/${xi}/${yi}`;
    const upstream = await fetch(url, {
      signal: AbortSignal.timeout(10_000),
      cache: "no-store",
    });

    if (!upstream.ok) {
      return transparent();
    }

    const buf = await upstream.arrayBuffer();
    if (buf.byteLength < 8) {
      return transparent();
    }

    return new Response(buf, {
      status: 200,
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "public, max-age=86400",
        "X-Parcel-Tile": "ok",
      },
    });
  } catch {
    return transparent();
  }
}

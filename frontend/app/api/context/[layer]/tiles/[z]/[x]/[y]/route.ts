/**
 * Context-layer tile proxy. Upstream errors become a transparent PNG so
 * MapLibre does not fill the console with tile failures.
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
      "Cache-Control": "no-store",
      "X-Context-Tile": "fallback",
    },
  });
}

type Ctx = {
  params: Promise<{ layer: string; z: string; x: string; y: string }>;
};

export async function GET(_request: Request, context: Ctx) {
  try {
    const { layer, z, x, y } = await context.params;
    if (!/^[a-z0-9-]{1,40}$/.test(layer)) {
      return transparent();
    }
    const yy = y.replace(/\.png$/i, "");
    const zi = Number(z);
    const xi = Number(x);
    const yi = Number(yy);
    if (![zi, xi, yi].every((n) => Number.isFinite(n) && n >= 0)) {
      return transparent();
    }

    const url = `${apiOrigin()}/layers/context/${layer}/tiles/${zi}/${xi}/${yi}`;
    const upstream = await fetch(url, {
      signal: AbortSignal.timeout(50_000),
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
        "Cache-Control": "public, max-age=3600",
        "X-Context-Tile": "ok",
      },
    });
  } catch {
    return transparent();
  }
}

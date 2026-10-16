import { SERVICE_BUSY } from "../../../lib/api";

/**
 * Resilient same-origin API proxy.
 * Replaces Next rewrites so upstream socket hang-ups become JSON 503
 * instead of browser TypeError: Failed to fetch.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function apiOrigin(): string {
  return (
    process.env.API_PROXY_TARGET ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

type Ctx = { params: Promise<{ path: string[] }> };

function visitorAddress(request: Request): string {
  const cloudflare = request.headers.get("cf-connecting-ip")?.trim();
  if (cloudflare) return cloudflare;
  const forwarded = request.headers.get("x-forwarded-for");
  const first = forwarded?.split(",")[0]?.trim();
  if (first) return first;
  const own = (request as Request & { ip?: string }).ip?.trim();
  return own || "unknown";
}

const GBP_LIVE_FLAG_OFF = {
  enabled: false,
  banner: null,
  rent_rate_wording: null,
  unit: null,
  unit_wording: null,
} as const;

async function proxy(request: Request, context: Ctx): Promise<Response> {
  try {
    const { path } = await context.params;
    const segments = path ?? [];
    if (segments.length === 0) {
      return Response.json({ detail: "Missing API path" }, { status: 400 });
    }

    const joined = segments.map(encodeURIComponent).join("/");
    // GBP-LIVE-V1: flag-off probe must never 404/503 — public £ stays hidden.
    if (joined === "platform/gbp-live" && request.method === "GET") {
      try {
        const upstream = await fetch(`${apiOrigin()}/platform/gbp-live`, {
          method: "GET",
          headers: { Accept: "application/json" },
          signal: AbortSignal.timeout(5_000),
          cache: "no-store",
        });
        if (!upstream.ok) {
          return Response.json(GBP_LIVE_FLAG_OFF, { status: 200 });
        }
        const buf = await upstream.arrayBuffer();
        return new Response(buf, {
          status: 200,
          headers: {
            "Content-Type":
              upstream.headers.get("Content-Type") || "application/json",
          },
        });
      } catch {
        return Response.json(GBP_LIVE_FLAG_OFF, { status: 200 });
      }
    }
    const incoming = new URL(request.url);
    const target = `${apiOrigin()}/${joined}${incoming.search}`;

    // Heavy layer endpoints need more headroom than health/square
    const heavy =
      joined.includes("councils-agr") ||
      joined.includes("w3w-grid") ||
      joined.includes("layers/open") ||
      joined.includes("layers/context") ||
      joined.includes("assessment/report");
    // Ordinary client wait was 25s. Heavy routes stay at 90s.
    const timeoutMs = heavy ? 90_000 : 60_000;

    const headers: Record<string, string> = {
      Accept: request.headers.get("Accept") || "application/json",
      "X-Forwarded-For": visitorAddress(request),
    };
    const proxySecret = process.env.SCOT_PROXY_SECRET;
    if (proxySecret) headers["X-Scotland-Proxy"] = proxySecret;

    const init: RequestInit = {
      method: request.method,
      signal: AbortSignal.timeout(timeoutMs),
      cache: "no-store",
      headers,
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = await request.arrayBuffer();
      const ct = request.headers.get("Content-Type");
      if (ct) headers["Content-Type"] = ct;
    }

    const upstream = await fetch(target, init);
    const buf = await upstream.arrayBuffer();
    const responseHeaders = new Headers();
    const ct = upstream.headers.get("Content-Type");
    if (ct) responseHeaders.set("Content-Type", ct);
    const cache = upstream.headers.get("Cache-Control");
    // HOME-TUNNEL: GET API responses cache for 5 minutes unless upstream forbids it.
    const method = request.method.toUpperCase();
    const upstreamForbids =
      !!cache && /\b(no-store|private)\b/i.test(cache);
    if ((method === "GET" || method === "HEAD") && !upstreamForbids) {
      responseHeaders.set("Cache-Control", "public, max-age=300");
    } else if (cache) {
      responseHeaders.set("Cache-Control", cache);
    }

    return new Response(buf, { status: upstream.status, headers: responseHeaders });
  } catch {
    const quiet = layersAddQuietWhenApiDown(new URL(request.url).pathname);
    if (quiet) return quiet;
    return Response.json({ detail: SERVICE_BUSY, ok: false }, { status: 503 });
  }
}

/**
 * When the API process is down, map chrome must not see 503 for the
 * LAYERS-ADD manifest. Vacant land stays listed; other extracts stay absent.
 * A live API response, including a real 404, is passed through above.
 */
function layersAddQuietWhenApiDown(pathname: string): Response | null {
  if (pathname.endsWith("/layers/add/tiles-manifest")) {
    return Response.json(
      {
        version: 1,
        sources: [{ layer_id: "vdl", display_id: "vdl" }],
      },
      { status: 200 },
    );
  }
  if (pathname.includes("/layers/add/viewport/")) {
    return Response.json(
      { type: "FeatureCollection", features: [] },
      { status: 200 },
    );
  }
  return null;
}

export async function GET(request: Request, context: Ctx) {
  return proxy(request, context);
}

export async function HEAD(request: Request, context: Ctx) {
  return proxy(request, context);
}

export async function POST(request: Request, context: Ctx) {
  return proxy(request, context);
}

export async function PUT(request: Request, context: Ctx) {
  return proxy(request, context);
}

export async function PATCH(request: Request, context: Ctx) {
  return proxy(request, context);
}

export async function DELETE(request: Request, context: Ctx) {
  return proxy(request, context);
}

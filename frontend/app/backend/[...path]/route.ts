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

async function proxy(request: Request, context: Ctx): Promise<Response> {
  try {
    const { path } = await context.params;
    const segments = path ?? [];
    if (segments.length === 0) {
      return Response.json({ detail: "Missing API path" }, { status: 400 });
    }

    const joined = segments.map(encodeURIComponent).join("/");
    const incoming = new URL(request.url);
    const target = `${apiOrigin()}/${joined}${incoming.search}`;

    // Heavy layer endpoints need more headroom than health/square
    const heavy =
      joined.includes("councils-agr") ||
      joined.includes("w3w-grid") ||
      joined.includes("layers/open") ||
      joined.includes("layers/context") ||
      joined.includes("assessment/report");
    const timeoutMs = heavy ? 90_000 : 25_000;

    const init: RequestInit = {
      method: request.method,
      signal: AbortSignal.timeout(timeoutMs),
      cache: "no-store",
      headers: {
        Accept: request.headers.get("Accept") || "application/json",
      },
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = await request.arrayBuffer();
      const ct = request.headers.get("Content-Type");
      if (ct) {
        (init.headers as Record<string, string>)["Content-Type"] = ct;
      }
    }

    const upstream = await fetch(target, init);
    const buf = await upstream.arrayBuffer();
    const headers = new Headers();
    const ct = upstream.headers.get("Content-Type");
    if (ct) headers.set("Content-Type", ct);
    const cache = upstream.headers.get("Cache-Control");
    if (cache) headers.set("Cache-Control", cache);

    return new Response(buf, { status: upstream.status, headers });
  } catch (err) {
    const message =
      err instanceof Error && err.name === "TimeoutError"
        ? "API request timed out. Try again or zoom in (smaller area)."
        : "API unreachable. Start the backend on port 8000, then retry.";
    return Response.json({ detail: message, ok: false }, { status: 503 });
  }
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

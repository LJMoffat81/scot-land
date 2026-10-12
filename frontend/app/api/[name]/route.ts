/**
 * Public preview aliases documented in docs/OPEN_LAYERS.md
 * (/api/roll.json, /api/catalog.json, …). Proxy to the FastAPI platform app.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const OPEN_API = new Set([
  "roll.json",
  "roll.csv",
  "public-land.json",
  "vdl.json",
  "vdl-councils.json",
  "place.json",
  "registers.json",
  "common-good.json",
  "catalog.json",
]);

function apiOrigin(): string {
  return (
    process.env.API_PROXY_TARGET ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

type Ctx = { params: Promise<{ name: string }> };

export async function GET(request: Request, context: Ctx) {
  const { name } = await context.params;
  if (!OPEN_API.has(name)) {
    return Response.json({ detail: "Not found" }, { status: 404 });
  }
  const incoming = new URL(request.url);
  const target = `${apiOrigin()}/api/${name}${incoming.search}`;
  try {
    const upstream = await fetch(target, {
      signal: AbortSignal.timeout(90_000),
      cache: "no-store",
      headers: { Accept: request.headers.get("Accept") || "application/json" },
    });
    const buf = await upstream.arrayBuffer();
    const headers = new Headers();
    const ct = upstream.headers.get("Content-Type");
    if (ct) headers.set("Content-Type", ct);
    const cache = upstream.headers.get("Cache-Control");
    if (cache) headers.set("Cache-Control", cache);
    return new Response(buf, { status: upstream.status, headers });
  } catch {
    return Response.json(
      { detail: "API unreachable. Start the backend on port 8000.", ok: false },
      { status: 503 },
    );
  }
}

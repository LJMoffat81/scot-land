/**
 * GBP-LIVE-V1 settings probe — always HTTP 200.
 *
 * Source of truth remains backend ``GET /platform/gbp-live`` (yaml flag).
 * When the API is down, unreachable, or returns an error, this route still
 * answers ``{ enabled: false }`` so visitor shells and e2e 404 traps stay green
 * while public £ stays hidden (flag default OFF).
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const FLAG_OFF = {
  enabled: false,
  banner: null,
  yield_wording: null,
} as const;

function apiOrigin(): string {
  return (
    process.env.API_PROXY_TARGET ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

export async function GET(): Promise<Response> {
  try {
    const upstream = await fetch(`${apiOrigin()}/platform/gbp-live`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(5_000),
      cache: "no-store",
    });
    if (!upstream.ok) {
      return Response.json(FLAG_OFF, { status: 200 });
    }
    const body = (await upstream.json()) as {
      enabled?: boolean;
      banner?: string | null;
      yield_wording?: string | null;
    };
    return Response.json(
      {
        enabled: Boolean(body?.enabled),
        banner: body?.banner ?? null,
        yield_wording: body?.yield_wording ?? null,
      },
      { status: 200 },
    );
  } catch {
    return Response.json(FLAG_OFF, { status: 200 });
  }
}

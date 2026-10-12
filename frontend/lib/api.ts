/**
 * Resolve API base URL for local + production.
 *
 * Local browser: same-origin `/backend` (Next.js rewrite → FastAPI).
 * That avoids CORS, Private Network Access blocks, and localhost vs 127.0.0.1
 * mismatches that surface as TypeError: Failed to fetch.
 *
 * Production / non-local: NEXT_PUBLIC_API_URL (e.g. Railway).
 */
export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1" || host === "[::1]") {
      return "/backend";
    }
    // Deployed frontend talking to a separate API host
    if (process.env.NEXT_PUBLIC_API_URL) {
      return process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");
    }
    // Same-origin if API is reverse-proxied in production too
    return "/backend";
  }

  // Server components / SSR: hit the API directly
  return (
    process.env.API_PROXY_TARGET ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

export class ApiError extends Error {
  status?: number;
  url: string;

  constructor(message: string, url: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.url = url;
    this.status = status;
  }
}

export const SERVICE_BUSY = "Service busy, please try again";

function isDevFacing(detail: string): boolean {
  const lower = detail.toLowerCase();
  return (
    lower.includes("port 8000") ||
    lower.includes("api offline") ||
    lower.includes("timed out") ||
    lower.includes("timeout") ||
    lower.includes("api unreachable") ||
    lower.includes("failed to fetch") ||
    lower.includes("networkerror") ||
    lower.includes("network request failed") ||
    lower.includes("load failed") ||
    lower.includes("traceback") ||
    lower.includes("exception") ||
    lower.includes("typeerror") ||
    lower.includes("valueerror") ||
    lower.includes("econnrefused") ||
    lower.includes("socket hang")
  );
}

export function isServiceFailure(err: unknown): boolean {
  return err instanceof ApiError && (err.status == null || err.status >= 500);
}

/** Copy safe to show a visitor. Service failures never include dev or exception text. */
export function visitorFacingError(err: unknown): string {
  const message = err instanceof Error ? err.message.trim() : "";
  if (message.toLowerCase().includes("outside scotland")) {
    return "That point is outside Scotland. Search a Scottish postcode or click the map.";
  }
  if (!message || isDevFacing(message) || isServiceFailure(err)) return SERVICE_BUSY;
  return message;
}

export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const base = getApiBaseUrl().replace(/\/$/, "");
  const url = path.startsWith("http")
    ? path
    : `${base}${path.startsWith("/") ? "" : "/"}${path}`;

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      // Explicit so rewrites + CORS preflight stay simple
      credentials: init?.credentials ?? "omit",
      headers: {
        Accept: "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(SERVICE_BUSY, url);
  }

  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* ignore non-JSON error bodies */
    }
    if (response.status >= 500 || !detail.trim() || isDevFacing(detail)) {
      detail = SERVICE_BUSY;
    }
    throw new ApiError(detail, url, response.status);
  }

  return response;
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);
  return (await response.json()) as T;
}

export async function pingApi(): Promise<{ ok: boolean; message: string }> {
  try {
    const data = await apiJson<{ status?: string; version?: string }>("/health");
    return {
      ok: data.status === "ok",
      message: data.version ? `API v${data.version}` : "API connected",
    };
  } catch (err) {
    return {
      ok: false,
      message: visitorFacingError(err),
    };
  }
}

/**
 * Which optional API routers this server mounts (from /health `routers`). The legacy
 * ground-rent (AGR) router is optional: when it is not loaded, its endpoints (/square,
 * /place, /layers/councils, parcel and context tiles) 404, so the map must not call them.
 * Cached for the page; a failed probe is retried on the next call.
 */
export type ApiCapabilities = { reachable: boolean; agr: boolean; platform: boolean };

let capabilitiesPromise: Promise<ApiCapabilities> | null = null;

export function fetchCapabilities(): Promise<ApiCapabilities> {
  if (!capabilitiesPromise) {
    capabilitiesPromise = apiJson<{ routers?: Record<string, { loaded?: boolean }> }>("/health")
      .then((data) => ({
        reachable: true,
        agr: data.routers?.["api.agr_routes"]?.loaded === true,
        platform: data.routers?.["api.platform_routes"]?.loaded === true,
      }))
      .catch(() => {
        capabilitiesPromise = null;
        return { reachable: false, agr: false, platform: false };
      });
  }
  return capabilitiesPromise;
}

/** Postcode-only search (postcodes.io) when the legacy place search is not mounted. */
export const POSTCODES_ONLY =
  "Search finds full UK postcodes only (e.g. G2 1DU). Or click the map.";

export function looksLikeFullPostcode(text: string): boolean {
  return /^[A-Z]{1,2}[0-9][A-Z0-9]?\s*[0-9][A-Z]{2}$/.test(text.trim().toUpperCase().replace(/\s+/g, " "));
}

/** Parse "lat, lng" or "lat lng" for the public search box (Scotland-ish bounds). */
export function parseCoordinates(
  text: string,
): { lat: number; lng: number } | null {
  const m = text
    .trim()
    .match(/^(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)$/);
  if (!m) return null;
  const lat = Number(m[1]);
  const lng = Number(m[2]);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  // Rough Scotland envelope — same spirit as backend bounds checks.
  if (lat < 54.4 || lat > 61.0 || lng < -9.0 || lng > 0.2) return null;
  return { lat, lng };
}

/** Shown only where a visitor asks for a legacy feature this server does not mount. */
export const AGR_UNAVAILABLE =
  "Address search and the ground-rent breakdown aren't available on this server yet. Click the map to look up a data zone.";

export type EngineStamp = {
  engine_version?: string | null;
  valuation?: {
    version?: string | null;
    inputs_hash?: string | null;
  } | null;
  policy?: {
    version?: string | null;
    inputs_hash?: string | null;
  } | null;
  config?: {
    agr_yaml_sha256?: string | null;
    layers_yaml_sha256?: string | null;
  } | null;
  data?: Record<string, unknown> | null;
  commit?: string | null;
  commit_full?: string | null;
};

function stampText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text) return null;
  const lowered = text.toLowerCase();
  if (lowered === "unknown" || lowered === "dev-unknown") return null;
  return text;
}

function parsedDataDate(value: unknown): { at: number; label: string } | null {
  const text = stampText(value);
  if (!text) return null;
  const dayMatch = /^(\d{4})-(\d{2})-(\d{2})(?:$|[T\s].*)/.exec(text);
  if (dayMatch) {
    const year = Number(dayMatch[1]);
    const month = Number(dayMatch[2]);
    const day = Number(dayMatch[3]);
    if (month < 1 || month > 12) return null;
    const probe = new Date(Date.UTC(year, month - 1, day));
    if (
      probe.getUTCFullYear() !== year ||
      probe.getUTCMonth() !== month - 1 ||
      probe.getUTCDate() !== day
    ) {
      return null;
    }
    return {
      at: year * 10000 + month * 100 + day,
      label: `${dayMatch[1]}-${dayMatch[2]}-${dayMatch[3]}`,
    };
  }
  const monthMatch = /^(\d{4})-(\d{2})$/.exec(text);
  if (!monthMatch) return null;
  const year = Number(monthMatch[1]);
  const month = Number(monthMatch[2]);
  if (month < 1 || month > 12) return null;
  return {
    at: year * 10000 + month * 100,
    label: `${monthMatch[1]}-${monthMatch[2]}`,
  };
}

function latestDataDate(data: EngineStamp["data"]): string | null {
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  let bestAt = -1;
  let bestLabel: string | null = null;
  for (const value of Object.values(data)) {
    const parsed = parsedDataDate(value);
    if (!parsed || parsed.at <= bestAt) continue;
    bestAt = parsed.at;
    bestLabel = parsed.label;
  }
  return bestLabel;
}

export function engineVersionLine(
  stamp: EngineStamp | null | undefined,
): string {
  if (!stamp || typeof stamp !== "object") return "";
  const parts: string[] = [];
  const engine = stampText(stamp.engine_version);
  if (engine) parts.push(`Engine ${engine}`);
  const method = stampText(stamp.valuation?.version);
  if (method) parts.push(`method ${method}`);
  const dataAsOf = latestDataDate(stamp.data);
  if (dataAsOf) parts.push(`data as of ${dataAsOf}`);
  const build = stampText(stamp.commit);
  if (build) parts.push(`build ${build}`);
  return parts.join(" \u00b7 ");
}

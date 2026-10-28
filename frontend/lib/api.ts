/**
 * Resolve API base URL for local + production.
 *
 * Local browser: same-origin `/backend` (Next.js rewrite → FastAPI).
 * That avoids CORS, Private Network Access blocks, and localhost vs 127.0.0.1
 * mismatches that surface as TypeError: Failed to fetch.
 *
 * Production / non-local: NEXT_PUBLIC_API_URL (e.g. Railway).
 */

/** HTTP statuses retried for place lookup (SHARE-FIX). */
export const PLACE_LOOKUP_RETRY_STATUSES = [502, 503, 504] as const;

export type ApiFetchInit = RequestInit & {
  /** Retry these HTTP statuses with exponential backoff (place lookup). */
  retryStatuses?: readonly number[];
  /** Attempts including the first try (default 3 when retryStatuses set). */
  maxAttempts?: number;
};

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

/** Visitor copy after place-lookup retries exhaust (replaces "Service busy"). */
export const TRY_AGAIN = "Try again";

/** @deprecated Prefer TRY_AGAIN — kept as alias for existing imports. */
export const SERVICE_BUSY = TRY_AGAIN;

/** Exact visitor copy when Housing land audit PostGIS is unloaded (HLA 503). */
export const HLA_NOT_LOADED =
  "Housing land audit isn't loaded yet. We don't fill gaps with guesses.";

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

/** True when the API returned HTTP service-unavailable (tiles / layer not loaded). */
export function isServiceUnavailable(err: unknown): boolean {
  return err instanceof ApiError && err.status === 503;
}

/**
 * Bounds / place 400 from `/platform/place` or `/api/place.json`
 * (`Coordinates appear to be outside Scotland.`).
 */
export function isOutsideScotlandError(err: unknown): boolean {
  if (!(err instanceof ApiError) || err.status !== 400) return false;
  return err.message.toLowerCase().includes("outside scotland");
}

/** Copy safe to show a visitor. Service failures never include dev or exception text. */
export function visitorFacingError(err: unknown): string {
  const message = err instanceof Error ? err.message.trim() : "";
  if (
    isOutsideScotlandError(err) ||
    message.toLowerCase().includes("outside scotland")
  ) {
    // Keep in sync with PLACE_CARD_OUT_OF_SCOTLAND_LINE (placeCard.ts).
    return "We only cover land so far. Scotland's sea rents (offshore wind, oil and gas, fish farms and seabed) will come later as their own map layer.";
  }
  if (!message || isDevFacing(message) || isServiceFailure(err)) return TRY_AGAIN;
  return message;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/** Backoff delays (ms) between place-lookup retries after 502/503/504. */
export function placeLookupBackoffMs(attemptIndex: number): number {
  // attemptIndex 0 = after first failure → 250ms, then 500, 1000, …
  return Math.min(2000, 250 * 2 ** attemptIndex);
}

function stripFetchInit(init?: ApiFetchInit): RequestInit {
  if (!init) return {};
  const { retryStatuses: _r, maxAttempts: _m, ...rest } = init;
  return rest;
}

export async function apiFetch(
  path: string,
  init?: ApiFetchInit,
): Promise<Response> {
  const base = getApiBaseUrl().replace(/\/$/, "");
  const url = path.startsWith("http")
    ? path
    : `${base}${path.startsWith("/") ? "" : "/"}${path}`;

  const retryStatuses = new Set(init?.retryStatuses ?? []);
  const maxAttempts =
    init?.maxAttempts ?? (retryStatuses.size > 0 ? 3 : 1);
  const fetchInit = stripFetchInit(init);

  let lastError: unknown;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    let response: Response;
    try {
      response = await fetch(url, {
        ...fetchInit,
        // Explicit so rewrites + CORS preflight stay simple
        credentials: fetchInit.credentials ?? "omit",
        headers: {
          Accept: "application/json",
          ...(fetchInit.headers ?? {}),
        },
      });
    } catch {
      throw new ApiError(TRY_AGAIN, url);
    }

    if (response.ok) return response;

    const retryable =
      retryStatuses.has(response.status) && attempt + 1 < maxAttempts;
    if (retryable) {
      await sleep(placeLookupBackoffMs(attempt));
      continue;
    }

    let detail = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* ignore non-JSON error bodies */
    }
    // Keep honest HLA unload copy; other 5xx stay generic Try again.
    if (detail.trim() === HLA_NOT_LOADED) {
      throw new ApiError(detail, url, response.status);
    }
    if (response.status >= 500 || !detail.trim() || isDevFacing(detail)) {
      detail = TRY_AGAIN;
    }
    lastError = new ApiError(detail, url, response.status);
    throw lastError;
  }

  throw lastError instanceof ApiError
    ? lastError
    : new ApiError(TRY_AGAIN, url);
}

/** Place / search lookup with SHARE-FIX retries on 502/503/504. */
export function placeLookupFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  return apiFetch(path, {
    ...init,
    retryStatuses: PLACE_LOOKUP_RETRY_STATUSES,
    maxAttempts: 3,
  });
}

export async function apiJson<T>(
  path: string,
  init?: ApiFetchInit,
): Promise<T> {
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
 * Which optional API routers this server mounts. HEALTH-TRIM (#166): `/health`
 * is status + version only, so AGR is detected via GET `/layers/catalog` (a
 * public path unique to that router). When AGR is not loaded, public
 * place/search endpoints 404, so the map must not call them. The public shell
 * never fetches council AGR metrics (/layers/councils) or paints rent £/m² —
 * modelled AGR £ stays internal-only. Cached for the page; a failed probe is
 * retried on the next call.
 *
 * `platform` is reserved for callers that need the open-platform router; the
 * map shell does not read it, so we do not probe a platform-only path (that
 * would 404 in e2e stubs that only mock health + catalog).
 */
export type ApiCapabilities = { reachable: boolean; agr: boolean; platform: boolean };

let capabilitiesPromise: Promise<ApiCapabilities> | null = null;

async function probeOk(path: string): Promise<boolean> {
  const base = getApiBaseUrl().replace(/\/$/, "");
  const url = `${base}${path.startsWith("/") ? "" : "/"}${path}`;
  try {
    const response = await fetch(url, {
      credentials: "omit",
      headers: { Accept: "application/json" },
    });
    return response.ok;
  } catch {
    return false;
  }
}

export function fetchCapabilities(): Promise<ApiCapabilities> {
  if (!capabilitiesPromise) {
    capabilitiesPromise = (async () => {
      const reachable = await probeOk("/health");
      if (!reachable) {
        capabilitiesPromise = null;
        return { reachable: false, agr: false, platform: false };
      }
      const agr = await probeOk("/layers/catalog");
      return { reachable: true, agr, platform: false };
    })().catch(() => {
      capabilitiesPromise = null;
      return { reachable: false, agr: false, platform: false };
    });
  }
  return capabilitiesPromise;
}

/** Postcode-only search (postcodes.io) when the legacy place search is not mounted. */
export const POSTCODES_ONLY =
  "Search finds full UK postcodes only (e.g. G2 1DU). Or tap or click the map.";

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
  // Wider than the API Scotland bounds check so near-offshore / west-of-bounds
  // pastes (SW-019, e.g. lng=-9.196485) still open selectPlace and show the
  // outside-Scotland plain line instead of "No place matched".
  if (lat < 54.0 || lat > 61.5 || lng < -11.0 || lng > 1.0) return null;
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

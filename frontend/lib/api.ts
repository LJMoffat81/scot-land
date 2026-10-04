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

function isNetworkError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const msg = err.message.toLowerCase();
  return (
    err.name === "TypeError" ||
    msg.includes("failed to fetch") ||
    msg.includes("networkerror") ||
    msg.includes("load failed") ||
    msg.includes("network request failed")
  );
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
  } catch (err) {
    const hint =
      base === "/backend"
        ? "Start the FastAPI backend on port 8000, then click Retry."
        : `Cannot reach the AGR API at ${base}. Start the backend (port 8000) and refresh.`;
    throw new ApiError(
      isNetworkError(err)
        ? `API unreachable. ${hint}`
        : err instanceof Error
          ? err.message
          : "API request failed",
      url,
    );
  }

  if (!response.ok) {
    let detail = `API error ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string; ok?: boolean };
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore non-JSON error bodies */
    }
    // 503 from our proxy = soft API issue, clearer message
    if (response.status === 503 && !detail.startsWith("API")) {
      detail = `API unreachable. ${detail}`;
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
      message: err instanceof Error ? err.message : "API unreachable",
    };
  }
}

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

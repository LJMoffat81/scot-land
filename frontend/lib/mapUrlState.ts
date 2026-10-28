/**
 * MAP-CARDS + MAP-VISION-1b URL contract (E1 + addendum A2 + MV-28/MV-29).
 * Unknown params are ignored for behaviour but kept on rewrite.
 */

import {
  validateBearingParam,
  validatePitchParam,
} from "./default3dView";
import type { MapBasemapId } from "./mapBasemap";
import {
  DEFAULT_PUBLIC_CONTEXT_METRIC_ID,
  PUBLIC_CONTEXT_METRIC_IDS,
  type MetricId,
} from "./mapColourRamps";
import {
  defaultOnLayerIds,
  resolveMapLayerId,
} from "./mapLayerRegistry";

export type MapPanelUrl = "place" | "layers" | null;

export type MapUrlState = {
  place: string | null;
  layers: string[];
  /** MV-28 alias for active layers (`?l=` or `?layers=`). */
  l: string[];
  /** MV-28 basemap (`?b=light|aerial`, default `"light"`). */
  b: MapBasemapId;
  /** MV-28 main measure (`?m=pop_density|simd|house_price|land_share`). */
  m: MetricId;
  z: number | null;
  /** DEFAULT-3D-VIEW pitch in degrees [0, 60] from `p` or `pitch`. */
  p: number | null;
  pitch: number | null;
  /** DEFAULT-3D-VIEW bearing in degrees [-180, 180] from `br` or `bearing`. */
  br: number | null;
  bearing: number | null;
  /** View centre [lng, lat] from `c` or lat/lon. */
  center: { lng: number; lat: number } | null;
  panel: MapPanelUrl;
  /** Params not in the known contract — preserved on rewrite. */
  unknown: Record<string, string>;
};

const KNOWN = new Set([
  "place",
  "layers",
  "l",
  "b",
  "m",
  "p",
  "pitch",
  "br",
  "bearing",
  "z",
  "c",
  "lat",
  "lng",
  "lon",
  "panel",
  // legacy aliases still read/cleared by the shell
  "words",
  "vacant",
  "community",
  "public",
  "band",
]);

/**
 * Camera centres outside this box are not a Scotland view.
 * Includes the Gulf of Guinea (0, 0). Inclusive edges are still Scotland.
 */
export const SCOTLAND_VIEW_BBOX = {
  minLng: -9.5,
  maxLng: -0.5,
  minLat: 54.5,
  maxLat: 61.0,
} as const;

export function isScotlandViewCenter(lng: number, lat: number): boolean {
  return (
    Number.isFinite(lng) &&
    Number.isFinite(lat) &&
    lng >= SCOTLAND_VIEW_BBOX.minLng &&
    lng <= SCOTLAND_VIEW_BBOX.maxLng &&
    lat >= SCOTLAND_VIEW_BBOX.minLat &&
    lat <= SCOTLAND_VIEW_BBOX.maxLat
  );
}

/** SW-060 — five decimal places is about one metre, inside a 5 m reopen. */
export function formatMapCenterParam(lng: number, lat: number): string {
  return `${lng.toFixed(5)},${lat.toFixed(5)}`;
}

/** MV-28 strict validator for basemap parameter (`light` | `aerial`, `simple` alias -> `light`). */
export function validateBasemapParam(raw: unknown): MapBasemapId {
  if (typeof raw !== "string" || !raw.trim()) {
    throw new Error("MAP-URL: basemap must be 'light' or 'aerial'");
  }
  const v = raw.trim().toLowerCase();
  if (v === "light" || v === "simple") return "light";
  if (v === "aerial") return "aerial";
  throw new Error(`MAP-URL: invalid basemap '${raw.trim()}'`);
}

export function parseBasemapParam(raw: string | null): MapBasemapId {
  if (!raw || !raw.trim()) return "light";
  try {
    return validateBasemapParam(raw);
  } catch {
    return "light";
  }
}

/** MV-28 strict validator for main measure parameter (`pop_density` | `simd` | `house_price` | `land_share`). */
export function validateMeasureParam(raw: unknown): MetricId {
  if (typeof raw !== "string" || !raw.trim()) {
    throw new Error("MAP-URL: measure must be a non-empty string");
  }
  const v = raw.trim() as MetricId;
  if (!PUBLIC_CONTEXT_METRIC_IDS.includes(v)) {
    throw new Error(`MAP-URL: invalid measure '${raw.trim()}'`);
  }
  return v;
}

export function parseMeasureParam(raw: string | null): MetricId {
  if (!raw || !raw.trim()) return DEFAULT_PUBLIC_CONTEXT_METRIC_ID;
  try {
    return validateMeasureParam(raw);
  } catch {
    return DEFAULT_PUBLIC_CONTEXT_METRIC_ID;
  }
}

export function parsePitchParam(raw: string | null): number | null {
  if (raw == null || !raw.trim()) return null;
  try {
    return validatePitchParam(raw);
  } catch {
    return null;
  }
}

export function parseBearingParam(raw: string | null): number | null {
  if (raw == null || !raw.trim()) return null;
  try {
    return validateBearingParam(raw);
  } catch {
    return null;
  }
}

function parseFinitePair(
  lngRaw: string,
  latRaw: string,
): { lng: number; lat: number } | null {
  if (lngRaw.trim() === "" || latRaw.trim() === "") return null;
  const lng = Number(lngRaw);
  const lat = Number(latRaw);
  if (!isScotlandViewCenter(lng, lat)) return null;
  return { lng, lat };
}

function parseCenter(params: URLSearchParams): { lng: number; lat: number } | null {
  // A present `c` wins. An out-of-Scotland `c` is ignored — do not fall
  // through to lat/lng, and do not invent a centre from missing keys.
  // Number(null) === 0, which is how a fresh URL became the Gulf of Guinea.
  if (params.has("c")) {
    const parts = (params.get("c") ?? "").split(",");
    if (parts.length !== 2) return null;
    return parseFinitePair(parts[0] ?? "", parts[1] ?? "");
  }
  const latRaw = params.get("lat");
  const lonRaw = params.get("lon") ?? params.get("lng");
  if (latRaw == null || lonRaw == null) return null;
  return parseFinitePair(lonRaw, latRaw);
}

/** Resolve comma-separated layer ids; unknown/coming-later ids dropped. */
export function parseLayerIdsParam(raw: string | null): string[] {
  if (!raw || !raw.trim()) return defaultOnLayerIds();
  const out: string[] = [];
  const seen = new Set<string>();
  for (const token of raw.split(",")) {
    const canonical = resolveMapLayerId(token.trim());
    if (!canonical || seen.has(canonical)) continue;
    seen.add(canonical);
    out.push(canonical);
  }
  return out.length ? out : defaultOnLayerIds();
}

export function readMapUrlState(
  search: string | URLSearchParams,
): MapUrlState {
  const params =
    typeof search === "string"
      ? new URLSearchParams(
          search.startsWith("?") ? search.slice(1) : search,
        )
      : search;

  const panelRaw = params.get("panel");
  const panel: MapPanelUrl =
    panelRaw === "place" || panelRaw === "layers" ? panelRaw : null;

  const zRaw = params.get("z");
  const zNum = zRaw != null ? Number(zRaw) : NaN;
  const p = parsePitchParam(params.get("p") ?? params.get("pitch"));
  const br = parseBearingParam(params.get("br") ?? params.get("bearing"));

  const layers = parseLayerIdsParam(params.get("l") ?? params.get("layers"));
  const b = parseBasemapParam(params.get("b"));
  const m = parseMeasureParam(params.get("m"));

  const unknown: Record<string, string> = {};
  params.forEach((value, key) => {
    if (!KNOWN.has(key)) unknown[key] = value;
  });

  return {
    place: params.get("place"),
    layers,
    l: layers,
    b,
    m,
    z: Number.isFinite(zNum) ? zNum : null,
    p,
    pitch: p,
    br,
    bearing: br,
    center: parseCenter(params),
    panel,
    unknown,
  };
}

export type WriteMapUrlOpts = {
  place?: string | null;
  layers?: readonly string[] | null;
  l?: readonly string[] | null;
  b?: MapBasemapId | null;
  m?: MetricId | null;
  z?: number | null;
  p?: number | null;
  pitch?: number | null;
  br?: number | null;
  bearing?: number | null;
  center?: { lng: number; lat: number } | null;
  panel?: MapPanelUrl;
  /** Extra unknown keys to keep (merged with current URL unknowns). */
  unknown?: Record<string, string>;
  /**
   * When true, drop known legacy keys (words/vacant/…) from the written URL.
   * Unknown keys are always preserved.
   */
  href?: string;
};

/**
 * Build a search string preserving unknown params (A2 + MV-28).
 * Known contract keys are rewritten from opts; omitted opts keep prior values
 * when `href` is provided.
 */
export function writeMapUrlSearch(opts: WriteMapUrlOpts): string {
  const base = new URL(
    opts.href ?? (typeof window !== "undefined" ? window.location.href : "http://local/"),
  );
  const prev = readMapUrlState(base.searchParams);
  const next = new URLSearchParams();

  const place = opts.place !== undefined ? opts.place : prev.place;
  const layers =
    opts.l !== undefined
      ? opts.l
      : opts.layers !== undefined
        ? opts.layers
        : prev.layers;
  const b = opts.b !== undefined ? (opts.b ?? "light") : prev.b;
  const m =
    opts.m !== undefined
      ? (opts.m ?? DEFAULT_PUBLIC_CONTEXT_METRIC_ID)
      : prev.m;
  const z = opts.z !== undefined ? opts.z : prev.z;
  const pRaw =
    opts.p !== undefined
      ? opts.p
      : opts.pitch !== undefined
        ? opts.pitch
        : prev.p;
  const brRaw =
    opts.br !== undefined
      ? opts.br
      : opts.bearing !== undefined
        ? opts.bearing
        : prev.br;
  const center = opts.center !== undefined ? opts.center : prev.center;
  const panel = opts.panel !== undefined ? opts.panel : prev.panel;
  const unknown = { ...prev.unknown, ...(opts.unknown ?? {}) };

  if (place) next.set("place", place);
  if (layers && layers.length) next.set("layers", layers.join(","));
  if (b === "aerial" || (opts.b === "light" && base.searchParams.has("b"))) {
    if (b === "aerial") next.set("b", "aerial");
  }
  if (m && m !== DEFAULT_PUBLIC_CONTEXT_METRIC_ID) {
    next.set("m", m);
  }
  if (z != null && Number.isFinite(z)) next.set("z", String(Math.round(z * 100) / 100));
  if (pRaw != null && Number.isFinite(pRaw) && pRaw >= 0 && pRaw <= 60) {
    const pRound = Math.round(pRaw * 10) / 10;
    if (
      pRound > 0 ||
      opts.p !== undefined ||
      opts.pitch !== undefined ||
      base.searchParams.has("p") ||
      base.searchParams.has("pitch")
    ) {
      next.set("p", String(pRound));
    }
  }
  if (brRaw != null && Number.isFinite(brRaw) && brRaw >= -180 && brRaw <= 180) {
    const brRound = Math.round(brRaw * 10) / 10;
    if (
      brRound !== 0 ||
      base.searchParams.has("br") ||
      base.searchParams.has("bearing")
    ) {
      next.set("br", String(Object.is(brRound, -0) ? 0 : brRound));
    }
  }
  // Never persist a centre outside Scotland (null island included).
  if (center && isScotlandViewCenter(center.lng, center.lat)) {
    next.set("c", formatMapCenterParam(center.lng, center.lat));
  }
  if (panel) next.set("panel", panel);

  for (const [key, value] of Object.entries(unknown)) {
    if (!next.has(key)) next.set(key, value);
  }

  const qs = next.toString();
  return qs ? `?${qs}` : "";
}

/**
 * MV-29: Build a normalized shareable URL string from `href`.
 */
export function buildShareableMapUrl(href: unknown): string {
  if (typeof href !== "string" || !href.trim()) {
    throw new Error("MAP-URL: href must be a valid URL string");
  }
  let parsed: URL;
  try {
    parsed = new URL(href.trim());
  } catch {
    throw new Error("MAP-URL: href must be a valid URL string");
  }
  const search = writeMapUrlSearch({ href: parsed.toString() });
  return `${parsed.origin}${parsed.pathname}${search}`;
}

export function replaceMapUrl(opts: WriteMapUrlOpts): void {
  if (typeof window === "undefined") return;
  const path = window.location.pathname;
  const search = writeMapUrlSearch({ ...opts, href: window.location.href });
  window.history.replaceState({}, "", `${path}${search}`);
}

export function pushMapUrl(opts: WriteMapUrlOpts): void {
  if (typeof window === "undefined") return;
  const path = window.location.pathname;
  const search = writeMapUrlSearch({ ...opts, href: window.location.href });
  window.history.pushState({}, "", `${path}${search}`);
}

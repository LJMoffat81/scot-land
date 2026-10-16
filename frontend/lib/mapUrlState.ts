/**
 * MAP-CARDS URL contract (E1 + addendum A2).
 * Unknown params are ignored for behaviour but kept on rewrite.
 */

import {
  defaultOnLayerIds,
  resolveMapLayerId,
} from "./mapLayerRegistry";

export type MapPanelUrl = "place" | "layers" | null;

export type MapUrlState = {
  place: string | null;
  layers: string[];
  z: number | null;
  /** View centre [lng, lat] from `c` or lat/lon. */
  center: { lng: number; lat: number } | null;
  panel: MapPanelUrl;
  /** Params not in the known contract — preserved on rewrite. */
  unknown: Record<string, string>;
};

const KNOWN = new Set([
  "place",
  "layers",
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

  const unknown: Record<string, string> = {};
  params.forEach((value, key) => {
    if (!KNOWN.has(key)) unknown[key] = value;
  });

  return {
    place: params.get("place"),
    layers: parseLayerIdsParam(params.get("layers")),
    z: Number.isFinite(zNum) ? zNum : null,
    center: parseCenter(params),
    panel,
    unknown,
  };
}

export type WriteMapUrlOpts = {
  place?: string | null;
  layers?: readonly string[] | null;
  z?: number | null;
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
 * Build a search string preserving unknown params (A2).
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
  const layers = opts.layers !== undefined ? opts.layers : prev.layers;
  const z = opts.z !== undefined ? opts.z : prev.z;
  const center = opts.center !== undefined ? opts.center : prev.center;
  const panel = opts.panel !== undefined ? opts.panel : prev.panel;
  const unknown = { ...prev.unknown, ...(opts.unknown ?? {}) };

  if (place) next.set("place", place);
  if (layers && layers.length) next.set("layers", layers.join(","));
  if (z != null && Number.isFinite(z)) next.set("z", String(Math.round(z * 100) / 100));
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

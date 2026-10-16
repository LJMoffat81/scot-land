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

function parseCenter(params: URLSearchParams): { lng: number; lat: number } | null {
  const c = params.get("c");
  if (c) {
    const parts = c.split(",").map((p) => Number(p.trim()));
    if (
      parts.length === 2 &&
      Number.isFinite(parts[0]) &&
      Number.isFinite(parts[1])
    ) {
      return { lng: parts[0]!, lat: parts[1]! };
    }
  }
  const lat = Number(params.get("lat"));
  const lon = Number(params.get("lon") ?? params.get("lng"));
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    return { lng: lon, lat };
  }
  return null;
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
  if (center) {
    next.set(
      "c",
      `${center.lng.toFixed(2)},${center.lat.toFixed(2)}`,
    );
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

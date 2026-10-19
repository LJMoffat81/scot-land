/**
 * MAP-CARDS basemap — OpenFreeMap Positron (light) ↔ Liberty (detailed).
 * Esri satellite is not offered (licence).
 */

export type MapBasemapId = "light" | "detailed";

export const MAP_BASEMAP_STYLE_URL: Readonly<Record<MapBasemapId, string>> = {
  light: "https://tiles.openfreemap.org/styles/positron",
  detailed: "https://tiles.openfreemap.org/styles/liberty",
};

/** Default rest basemap. */
export const DEFAULT_MAP_BASEMAP: MapBasemapId = "light";

/** Explicit map ceiling — GRID-BASE-1 supersedes addendum A3 (was 19). */
export const MAP_MAX_ZOOM = 20;

/** The other style from the current one. */
export function basemapSwitchTarget(current: MapBasemapId): MapBasemapId {
  return current === "light" ? "detailed" : "light";
}

/** User-facing name. The id stays `light`; the label is Simple. */
export function basemapLabel(id: MapBasemapId): "Simple" | "Detailed" {
  return id === "detailed" ? "Detailed" : "Simple";
}

/** Shown when the basemap style or its tiles do not load. */
export const BASEMAP_LOAD_NOTICE =
  "The background map didn't load. The land layers still work. Try reloading the page.";

/** No `style.load` within this long counts as a basemap failure. */
export const BASEMAP_STYLE_TIMEOUT_MS = 15_000;

export type BasemapNoticeState = {
  styleLoaded: boolean;
  notice: boolean;
};

export function initialBasemapNoticeState(): BasemapNoticeState {
  return { styleLoaded: false, notice: false };
}

/**
 * Notice turns on for a basemap error or a style-load timeout.
 * A later style.load hides it.
 */
export function reduceBasemapNotice(
  state: BasemapNoticeState,
  event:
    | { type: "style.load" }
    | { type: "timeout" }
    | { type: "error"; basemap: boolean },
): BasemapNoticeState {
  if (event.type === "style.load") {
    return { styleLoaded: true, notice: false };
  }
  if (event.type === "timeout") {
    if (state.styleLoaded) return state;
    return { styleLoaded: false, notice: true };
  }
  if (event.basemap) {
    return { styleLoaded: state.styleLoaded, notice: true };
  }
  return state;
}

/**
 * True when a MapLibre error event is the basemap style or one of its tiles.
 * AbortError is not a failure. Glyph and sprite errors without a tile source
 * are not the basemap.
 */
export function isBasemapFailureEvent(
  event: { error?: unknown; sourceId?: string | null },
  styleUrl: string,
): boolean {
  const line = mapErrorLogLine(event.error);
  if (!line) return false;
  if (styleUrl && line.includes(styleUrl)) return true;
  const sourceId = (event.sourceId ?? "").trim();
  if (sourceId && /tiles\.openfreemap\.org/i.test(line)) return true;
  return false;
}

export function basemapStyleUrl(id: MapBasemapId): string {
  return MAP_BASEMAP_STYLE_URL[id];
}

/**
 * OpenFreeMap draws building footprints from zoom 12.
 * Keep them off until just before the 3 m grid (zoom 17).
 */
export const BASEMAP_BUILDING_MIN_ZOOM = 16;

export type BasemapQuietDecision = "none" | "visible" | "leave";

/** Fields the quiet rule reads from a style layer. */
export type BasemapQuietLayer = {
  id: string;
  "source-layer"?: string;
};

/**
 * Hide OpenFreeMap residential land-use at every zoom so grey towns
 * are not read as Scot-LAND data. Hide building layers below
 * BASEMAP_BUILDING_MIN_ZOOM and show them again from that zoom.
 * "leave" means the layer is not one of those.
 */
export function basemapQuietVisibility(
  layer: BasemapQuietLayer,
  zoom: number,
): BasemapQuietDecision {
  const id = layer.id;
  const sourceLayer = layer["source-layer"] ?? "";
  if (
    id === "landuse_residential" ||
    (sourceLayer === "landuse" && id.includes("residential"))
  ) {
    return "none";
  }
  const building =
    sourceLayer === "building" || id === "building" || id.startsWith("building");
  if (!building) return "leave";
  if (Number.isFinite(zoom) && zoom >= BASEMAP_BUILDING_MIN_ZOOM) {
    return "visible";
  }
  return "none";
}

export type BasemapQuietMap = {
  getStyle(): { layers?: readonly BasemapQuietLayer[] } | null | undefined;
  getZoom(): number;
  getLayer(id: string): unknown;
  getLayoutProperty(id: string, name: "visibility"): unknown;
  setLayoutProperty(
    id: string,
    name: "visibility",
    value: "none" | "visible",
  ): void;
};

/** Apply the quiet rule to the loaded style. Safe to call again on zoom. */
export function applyBasemapQuiet(map: BasemapQuietMap): void {
  let layers: readonly BasemapQuietLayer[] | undefined;
  try {
    layers = map.getStyle()?.layers;
  } catch {
    return;
  }
  if (!layers) return;
  const zoom = map.getZoom();
  for (const layer of layers) {
    const decision = basemapQuietVisibility(layer, zoom);
    if (decision === "leave") continue;
    try {
      if (!map.getLayer(layer.id)) continue;
      if (map.getLayoutProperty(layer.id, "visibility") === decision) continue;
      map.setLayoutProperty(layer.id, "visibility", decision);
    } catch {
      // A zoom event can land while the style is swapping.
    }
  }
}

/**
 * MapLibre's own abort is `new Error("AbortError")`.
 * A cancelled fetch is a DOMException named AbortError.
 */
function isAbortError(err: unknown): boolean {
  if (err instanceof Error) {
    return err.name === "AbortError" || err.message === "AbortError";
  }
  return String(err ?? "").trim() === "AbortError";
}

/**
 * Text for a MapLibre "error" event.
 * MapLibre console.errors the Error object only when nothing listens.
 * AbortError is the only skip. Every other error is logged.
 */
export function mapErrorLogLine(err: unknown): string | null {
  if (isAbortError(err)) return null;
  if (err instanceof Error) {
    const url =
      "url" in err && typeof (err as { url?: unknown }).url === "string"
        ? ` ${(err as { url: string }).url}`
        : "";
    const message = `${err.name}: ${err.message}${url}`.trim();
    return message || err.name || "Error";
  }
  const message = String(err ?? "").trim();
  return message || "Error";
}

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

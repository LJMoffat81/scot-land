/**
 * MAP-CARDS basemap — OpenFreeMap Positron (light) ↔ Liberty (detailed).
 * Esri satellite is not offered (licence).
 */

export type MapBasemapId = "light" | "detailed";

export const MAP_BASEMAP_STYLE_URL: Readonly<Record<MapBasemapId, string>> = {
  light: "https://tiles.openfreemap.org/styles/positron",
  detailed: "https://tiles.openfreemap.org/styles/liberty",
};

/**
 * Cache-bust for the style document only. Tiles, sprites and glyphs stay on
 * the URLs inside that document. A new value makes a stale style fetch a new URL.
 */
const BASEMAP_STYLE_VERSION = "20261016";

/** Default rest basemap. */
export const DEFAULT_MAP_BASEMAP: MapBasemapId = "light";

/** Explicit map ceiling — GRID-BASE-1 supersedes addendum A3 (was 19). */
export const MAP_MAX_ZOOM = 20;

/** The style the switcher preview / caption points toward (not the current). */
export function basemapSwitchTarget(current: MapBasemapId): MapBasemapId {
  return current === "light" ? "detailed" : "light";
}

export function basemapCaption(target: MapBasemapId): "Detailed" | "Light" {
  return target === "detailed" ? "Detailed" : "Light";
}

export function basemapAriaLabel(target: MapBasemapId): string {
  return target === "detailed"
    ? "Map style: switch to Detailed"
    : "Map style: switch to Light";
}

export function basemapStyleUrl(id: MapBasemapId): string {
  const url = new URL(MAP_BASEMAP_STYLE_URL[id]);
  url.searchParams.set("v", BASEMAP_STYLE_VERSION);
  return url.toString();
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

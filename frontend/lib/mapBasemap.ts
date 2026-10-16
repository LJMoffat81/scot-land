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
  return MAP_BASEMAP_STYLE_URL[id];
}

const OPENFREEMAP_FONTS = "https://tiles.openfreemap.org/fonts/";
const FONT_FAMILY = /^[A-Za-z0-9 ._+-]{1,80}$/;
const FONT_RANGE = /^\d{1,6}-\d{1,6}\.pbf$/;

/**
 * Glyph ranges are fetched with fetch(), so a missing CORS header on the
 * tile host becomes a console error. Serve those files from this origin.
 */
export function proxiedBasemapFontUrl(url: string): string {
  if (!url.startsWith(OPENFREEMAP_FONTS)) return url;
  const rest = url.slice(OPENFREEMAP_FONTS.length).split(/[?#]/, 1)[0] ?? "";
  const parts = rest.split("/");
  if (parts.length !== 2) return url;
  let family: string;
  try {
    family = decodeURIComponent(parts[0] ?? "");
  } catch {
    return url;
  }
  const file = parts[1] ?? "";
  if (!FONT_FAMILY.test(family) || !FONT_RANGE.test(file)) return url;
  return `/basemap/fonts/${encodeURIComponent(family)}/${file}`;
}

export function basemapTransformRequest(url: string): { url: string } {
  return { url: proxiedBasemapFontUrl(url) };
}

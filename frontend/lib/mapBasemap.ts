/**
 * MAP-CARDS basemap — OpenFreeMap Positron (light) ↔ Liberty (detailed).
 * Esri satellite is not offered (licence).
 * The map requests the style through /api/ofm so TileJSON stays same-origin.
 * This file stays import-free so Node can load it directly in the credit check.
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

const OFM_STYLE_PREFIX = "https://tiles.openfreemap.org/";

export function basemapStyleUrl(id: MapBasemapId): string {
  const upstream = MAP_BASEMAP_STYLE_URL[id];
  if (!upstream.startsWith(OFM_STYLE_PREFIX)) return upstream;
  return `/api/ofm/${upstream.slice(OFM_STYLE_PREFIX.length)}`;
}

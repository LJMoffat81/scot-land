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

/** Explicit map ceiling (addendum A3). */
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

/**
 * Esri Basemap Styles API key — build-time NEXT_PUBLIC, empty when unset.
 * Whitespace counts as unset (MC5). E2E builds may inject a runtime override.
 */

export const ESRI_BASEMAP_API_KEY_ENV = "NEXT_PUBLIC_ESRI_BASEMAP_API_KEY";

/**
 * Raw key string (may include whitespace). Prefer {@link isEsriBasemapKeyConfigured}
 * for presence checks.
 */
export function readEsriBasemapApiKey() {
  if (
    typeof window !== "undefined" &&
    process.env.NEXT_PUBLIC_E2E_HOOKS === "1"
  ) {
    const injected = window.__E2E_ESRI_BASEMAP_API_KEY__;
    if (injected === null) return "";
    if (typeof injected === "string") return injected;
  }
  return process.env.NEXT_PUBLIC_ESRI_BASEMAP_API_KEY ?? "";
}

/** True when Aerial may be offered (non-empty after trim). */
export function isEsriBasemapKeyConfigured(key = readEsriBasemapApiKey()) {
  return key.trim().length > 0;
}

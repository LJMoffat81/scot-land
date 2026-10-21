/**
 * Esri Basemap Styles API key — build-time NEXT_PUBLIC, empty when unset.
 * Whitespace counts as unset (MC5). E2E builds may inject a runtime override.
 */

export const ESRI_BASEMAP_API_KEY_ENV = "NEXT_PUBLIC_ESRI_BASEMAP_API_KEY";

/**
 * Pure key resolution. Production uses envKey; the window override applies
 * only when hooksOn is true.
 *
 * @param {{ envKey?: string | undefined, hooksOn: boolean, injected?: string | null | undefined }} args
 * @returns {string}
 */
export function resolveEsriKey({ envKey, hooksOn, injected }) {
  if (hooksOn) {
    if (injected === null) return "";
    if (typeof injected === "string") return injected;
  }
  return envKey ?? "";
}

/**
 * Raw key string (may include whitespace). Prefer {@link isEsriBasemapKeyConfigured}
 * for presence checks.
 */
export function readEsriBasemapApiKey() {
  const envKey = process.env.NEXT_PUBLIC_ESRI_BASEMAP_API_KEY;
  const hooksOn = process.env.NEXT_PUBLIC_E2E_HOOKS === "1";
  const injected =
    typeof window !== "undefined"
      ? window.__E2E_ESRI_BASEMAP_API_KEY__
      : undefined;
  return resolveEsriKey({ envKey, hooksOn, injected });
}

/** True when Aerial may be offered (non-empty after trim). */
export function isEsriBasemapKeyConfigured(key = readEsriBasemapApiKey()) {
  return key.trim().length > 0;
}

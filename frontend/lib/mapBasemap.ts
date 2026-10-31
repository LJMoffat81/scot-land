/**
 * Map basemap — OpenFreeMap Positron (Simple) ↔ Esri World Imagery (Aerial).
 */

import {
  isEsriBasemapKeyConfigured,
  readEsriBasemapApiKey,
} from "./esriBasemapKey.mjs";

export type MapBasemapId = "light" | "aerial";

const POSITRON_STYLE_URL = "https://tiles.openfreemap.org/styles/positron";

const ESRI_IMAGERY_STYLE_BASE =
  "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles/arcgis/imagery";

/**
 * Style URLs without secrets. Aerial resolves the token at request time via
 * {@link basemapStyleUrl}; this map stays free of `token=` / `key=` for the
 * LAYERS-ADD-2 free-style guard.
 */
export const MAP_BASEMAP_STYLE_URL: Readonly<Record<MapBasemapId, string>> = {
  light: POSITRON_STYLE_URL,
  aerial: ESRI_IMAGERY_STYLE_BASE,
};

/** Default rest basemap. */
export const DEFAULT_MAP_BASEMAP: MapBasemapId = "light";

/** Explicit map ceiling — GRID-BASE-1 supersedes addendum A3 (was 19). */
export const MAP_MAX_ZOOM = 20;

/** Aerial failure / fallback notice (idea 78 / MC6). */
export const AERIAL_UNAVAILABLE_NOTICE =
  "Aerial map isn't available right now. Showing the simple map.";

/** How long Aerial style/tiles may fail before MC6 revert. */
export const AERIAL_FAIL_WINDOW_MS = 8_000;

/** The other style from the current one. */
export function basemapSwitchTarget(current: MapBasemapId): MapBasemapId {
  return current === "light" ? "aerial" : "light";
}

/** User-facing name. The id stays `light`; the label is Simple. */
export function basemapLabel(id: MapBasemapId): "Simple" | "Aerial" {
  return id === "aerial" ? "Aerial" : "Simple";
}

/** Visible text under the globe on the basemap switcher (CARD-CLARITY-31OCT-1A). */
export const BASEMAP_SWITCHER_VISIBLE_LABEL = "Aerial";

/** Shown when the Simple basemap style or its tiles do not load. */
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

export function esriImageryStyleUrl(token: string): string {
  const key = token.trim();
  const url = new URL(ESRI_IMAGERY_STYLE_BASE);
  url.searchParams.set("token", key);
  url.searchParams.set("language", "en");
  return url.toString();
}

export function basemapStyleUrl(id: MapBasemapId): string {
  if (id === "aerial") {
    const key = readEsriBasemapApiKey();
    if (!isEsriBasemapKeyConfigured(key)) {
      return POSITRON_STYLE_URL;
    }
    return esriImageryStyleUrl(key);
  }
  return POSITRON_STYLE_URL;
}

/**
 * Distinct non-empty attribution values from an Esri style's sources, in
 * style order, joined with "; ". Empty → treat as style failure (O1).
 */
export function esriStyleAttributionText(style: {
  sources?: Record<string, unknown> | null;
}): string | null {
  const sources = style.sources ?? {};
  const parts: string[] = [];
  const seen = new Set<string>();
  const entries = Object.entries(sources);
  // Prefer Esri-named sources when present (avoids overlay credits after load).
  const preferred = entries.filter(([id]) => /^esri/i.test(id));
  const list = preferred.length > 0 ? preferred : entries;
  for (const [, source] of list) {
    if (!source || typeof source !== "object") continue;
    const rec = source as { attribution?: unknown; copyrightText?: unknown };
    const attr =
      typeof rec.attribution === "string" ? rec.attribution : "";
    const copy =
      typeof rec.copyrightText === "string" ? rec.copyrightText : "";
    const raw = (attr || copy).trim();
    if (!raw || seen.has(raw)) continue;
    seen.add(raw);
    parts.push(raw);
  }
  return parts.length > 0 ? parts.join("; ") : null;
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
  if (/arcgis\.com/i.test(line)) return true;
  return false;
}

/** True when the error line looks like an Aerial / Esri load failure. */
export function isAerialFailureEvent(event: {
  error?: unknown;
  sourceId?: string | null;
}): boolean {
  const line = mapErrorLogLine(event.error);
  if (!line) return false;
  if (/arcgis\.com/i.test(line)) return true;
  const sourceId = (event.sourceId ?? "").trim();
  if (sourceId && /esri/i.test(sourceId)) return true;
  // HTTP status tokens Esri / MapLibre often surface
  if (/\b(401|403|498|499|5\d\d)\b/.test(line) && /arcgis|esri|imagery|basemap/i.test(line)) {
    return true;
  }
  // Invalid style JSON (T-M2) without a hostname in the message
  if (/Unexpected token|is not valid JSON|JSON\.parse/i.test(line)) {
    return true;
  }
  return false;
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

/**
 * Device-drawn 3 m BNG grid — GeoJSON builders and map constants (GRID-BASE-1).
 * No network. Lines only; never all cells.
 */

import {
  BNG_E_MAX,
  BNG_E_MIN,
  BNG_N_MAX,
  BNG_N_MIN,
  BNG_TRANSFORM,
  GRID3_METRES,
  bngToWgs84,
  floorToGrid3,
  grid3Key,
  grid3OsRef,
  inBngExtent,
  wgs84ToBng,
  type BngPoint,
} from "./bng";

export { BNG_TRANSFORM };

export const GRID3_LAYER_ID = "grid3";
export const GRID3_MIN_ZOOM = 17;
export const GRID3_HOVER_ZOOM = 18;
export const GRID3_TAP_ZOOM = 19;
export const GRID3_MAX_ZOOM = 20;

export const GRID3_SOURCE_LINES = "grid3-lines";
export const GRID3_SOURCE_HIGHLIGHT = "grid3-highlight";
export const GRID3_LAYER_LINES = "grid3-lines-layer";
export const GRID3_LAYER_LINES_HALO = "grid3-lines-halo";
export const GRID3_LAYER_HIGHLIGHT_FILL = "grid3-highlight-fill";
export const GRID3_LAYER_HIGHLIGHT_LINE = "grid3-highlight-line";
export const GRID3_LAYER_HIGHLIGHT_HALO = "grid3-highlight-halo";

/** Faint grid lines — navy token at 18% (Positron / Liberty). */
export const GRID3_LINE_COLOR = "#0b2340";
export const GRID3_LINE_OPACITY = 0.18;
export const GRID3_LINE_WIDTH = 1;

/** Imagery basemap rule (white @ 35% + 1px dark halo). */
export const GRID3_LINE_COLOR_IMAGERY = "#ffffff";
export const GRID3_LINE_OPACITY_IMAGERY = 0.35;
export const GRID3_LINE_HALO_COLOR = "#0b2340";

/** Highlight matches selected-zone style cues. */
export const GRID3_HIGHLIGHT_FILL = "#1d4f91";
export const GRID3_HIGHLIGHT_FILL_OPACITY = 0.18;
export const GRID3_HIGHLIGHT_OUTLINE = "#0b2340";
export const GRID3_HIGHLIGHT_OUTLINE_WIDTH = 2;
export const GRID3_HIGHLIGHT_HALO_WIDTH = 2;

export const GRID3_ZOOM_HINT = "Zoom in to see the grid";
export const GRID3_SUBLINE = "Shows when you zoom right in";
export const GRID3_LABEL = "3 m grid";

export const EMPTY_FC: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

export type Grid3Square = {
  key: string;
  ref: string;
  easting: number;
  northing: number;
  transform: typeof BNG_TRANSFORM;
};

/** Clamp a BNG range to the legal extent. */
function clampRange(
  min: number,
  max: number,
  lo: number,
  hi: number,
): { min: number; max: number } | null {
  const a = Math.max(min, lo);
  const b = Math.min(max, hi);
  if (a > b) return null;
  return { min: a, max: b };
}

/**
 * Build visible 3 m grid lines for a WGS84 viewport.
 * Projects all 4 corners → E/N min/max, pad 50%, emit line endpoints in WGS84.
 */
export function buildGrid3Lines(
  corners: ReadonlyArray<{ lng: number; lat: number }>,
): { collection: GeoJSON.FeatureCollection; vertexCount: number } {
  if (corners.length < 4) {
    return { collection: EMPTY_FC, vertexCount: 0 };
  }

  const bngCorners = corners.map((c) => wgs84ToBng(c.lng, c.lat));
  let eMin = Infinity;
  let eMax = -Infinity;
  let nMin = Infinity;
  let nMax = -Infinity;
  for (const p of bngCorners) {
    eMin = Math.min(eMin, p.easting);
    eMax = Math.max(eMax, p.easting);
    nMin = Math.min(nMin, p.northing);
    nMax = Math.max(nMax, p.northing);
  }

  const ePad = (eMax - eMin) * 0.5;
  const nPad = (nMax - nMin) * 0.5;
  eMin -= ePad;
  eMax += ePad;
  nMin -= nPad;
  nMax += nPad;

  const eRange = clampRange(eMin, eMax, BNG_E_MIN, BNG_E_MAX);
  const nRange = clampRange(nMin, nMax, BNG_N_MIN, BNG_N_MAX);
  if (!eRange || !nRange) {
    return { collection: EMPTY_FC, vertexCount: 0 };
  }

  const eStart = Math.ceil(eRange.min / GRID3_METRES) * GRID3_METRES;
  const nStart = Math.ceil(nRange.min / GRID3_METRES) * GRID3_METRES;

  const features: GeoJSON.Feature[] = [];
  let vertexCount = 0;

  for (let e = eStart; e <= eRange.max; e += GRID3_METRES) {
    const a = bngToWgs84(e, nRange.min);
    const b = bngToWgs84(e, nRange.max);
    features.push({
      type: "Feature",
      properties: { kind: "e", e },
      geometry: {
        type: "LineString",
        coordinates: [
          [a.lng, a.lat],
          [b.lng, b.lat],
        ],
      },
    });
    vertexCount += 2;
  }

  for (let n = nStart; n <= nRange.max; n += GRID3_METRES) {
    const a = bngToWgs84(eRange.min, n);
    const b = bngToWgs84(eRange.max, n);
    features.push({
      type: "Feature",
      properties: { kind: "n", n },
      geometry: {
        type: "LineString",
        coordinates: [
          [a.lng, a.lat],
          [b.lng, b.lat],
        ],
      },
    });
    vertexCount += 2;
  }

  return {
    collection: { type: "FeatureCollection", features },
    vertexCount,
  };
}

/** One-feature highlight polygon for a square SW corner. */
export function buildGrid3Highlight(
  easting: number,
  northing: number,
): GeoJSON.FeatureCollection {
  if (!inBngExtent(easting, northing)) return EMPTY_FC;
  const sw = floorToGrid3(easting, northing);
  const e0 = sw.easting;
  const n0 = sw.northing;
  const swW = bngToWgs84(e0, n0);
  const seW = bngToWgs84(e0 + GRID3_METRES, n0);
  const neW = bngToWgs84(e0 + GRID3_METRES, n0 + GRID3_METRES);
  const nwW = bngToWgs84(e0, n0 + GRID3_METRES);
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {
          key: grid3Key(e0, n0),
          ref: grid3OsRef(e0, n0),
          transform: BNG_TRANSFORM,
        },
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [swW.lng, swW.lat],
              [seW.lng, seW.lat],
              [neW.lng, neW.lat],
              [nwW.lng, nwW.lat],
              [swW.lng, swW.lat],
            ],
          ],
        },
      },
    ],
  };
}

/** Resolve square at WGS84, or null outside extent. */
export function squareAtWgs(lng: number, lat: number): Grid3Square | null {
  const { easting, northing } = wgs84ToBng(lng, lat);
  if (!inBngExtent(easting, northing)) return null;
  const sw: BngPoint = floorToGrid3(easting, northing);
  return {
    key: grid3Key(sw.easting, sw.northing),
    ref: grid3OsRef(sw.easting, sw.northing),
    easting: sw.easting,
    northing: sw.northing,
    transform: BNG_TRANSFORM,
  };
}

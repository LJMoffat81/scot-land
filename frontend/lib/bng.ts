/**
 * British National Grid (EPSG:27700) ↔ WGS84 via proj4 Helmert.
 * Transform version: helmert-v1. OSTN15 is required before any value ships.
 */

import proj4 from "proj4";

/** Recorded transform id — store alongside any saved key / analytics event. */
export const BNG_TRANSFORM = "helmert-v1" as const;

/** Square size in metres. */
export const GRID3_METRES = 3;

/** Valid BNG extent for lines / IDs (metres). */
export const BNG_E_MIN = 0;
export const BNG_E_MAX = 700_000;
export const BNG_N_MIN = 0;
export const BNG_N_MAX = 1_300_000;

/**
 * OSGB36 / BNG transverse Mercator + Helmert towgs84 (EPSG:27700 classic).
 * Only proj4 definition in the frontend (G14).
 */
export const BNG_PROJ4 =
  "+proj=tmerc +lat_0=49 +lon_0=-2 +k=0.9996012717 +x_0=400000 +y_0=-100000 " +
  "+ellps=airy +towgs84=446.448,-125.157,542.06,0.15,0.247,0.842,-20.489 " +
  "+units=m +no_defs";

const BNG_CRS = "EPSG:27700";

let defined = false;

function ensureDefs(): void {
  if (defined) return;
  proj4.defs(BNG_CRS, BNG_PROJ4);
  defined = true;
}

export type BngPoint = { easting: number; northing: number };
export type WgsPoint = { lng: number; lat: number };

/** WGS84 → BNG metres. */
export function wgs84ToBng(lng: number, lat: number): BngPoint {
  ensureDefs();
  const [easting, northing] = proj4("EPSG:4326", BNG_CRS, [lng, lat]);
  return { easting, northing };
}

/** BNG metres → WGS84. */
export function bngToWgs84(easting: number, northing: number): WgsPoint {
  ensureDefs();
  const [lng, lat] = proj4(BNG_CRS, "EPSG:4326", [easting, northing]);
  return { lng, lat };
}

/** True when the point lies inside the BNG draw/ID extent. */
export function inBngExtent(easting: number, northing: number): boolean {
  return (
    easting >= BNG_E_MIN &&
    easting <= BNG_E_MAX &&
    northing >= BNG_N_MIN &&
    northing <= BNG_N_MAX
  );
}

/** Floor easting/northing to the SW corner of the containing 3 m square. */
export function floorToGrid3(easting: number, northing: number): BngPoint {
  return {
    easting: Math.floor(easting / GRID3_METRES) * GRID3_METRES,
    northing: Math.floor(northing / GRID3_METRES) * GRID3_METRES,
  };
}

/** Data key: `g3:easting:northing` (multiples of 3). */
export function grid3Key(easting: number, northing: number): string {
  const sw = floorToGrid3(easting, northing);
  return `g3:${sw.easting}:${sw.northing}`;
}

/** Parse `g3:E:N` → SW corner, or null if invalid. */
export function parseGrid3Key(key: string): BngPoint | null {
  const m = /^g3:(\d+):(\d+)$/.exec(key);
  if (!m) return null;
  const easting = Number(m[1]);
  const northing = Number(m[2]);
  if (!Number.isFinite(easting) || !Number.isFinite(northing)) return null;
  if (easting % GRID3_METRES !== 0 || northing % GRID3_METRES !== 0) return null;
  return { easting, northing };
}

/**
 * OS grid letters for a 100 km square (no letter I).
 * Classic OS National Grid indexing.
 */
function gridLetters(easting: number, northing: number): string {
  let e100 = Math.floor(easting / 100_000);
  let n100 = Math.floor(northing / 100_000);

  const l1 =
    (19 - n100) - ((19 - n100) % 5) + Math.floor((e100 + 10) / 5);
  const l2 = (((19 - n100) * 5) % 25) + (e100 % 5);

  const letter = (n: number): string => {
    let idx = n;
    if (idx < 0 || idx > 24) return "?";
    if (idx > 7) idx += 1; // skip I
    return String.fromCharCode("A".charCodeAt(0) + idx);
  };

  return `${letter(l1)}${letter(l2)}`;
}

/**
 * Display OS grid reference of the SW corner, e.g. "NT 25890 73452".
 * Five figures within the 100 km square.
 */
export function grid3OsRef(easting: number, northing: number): string {
  const sw = floorToGrid3(easting, northing);
  const letters = gridLetters(sw.easting, sw.northing);
  const e5 = Math.floor(sw.easting % 100_000)
    .toString()
    .padStart(5, "0");
  const n5 = Math.floor(sw.northing % 100_000)
    .toString()
    .padStart(5, "0");
  return `${letters} ${e5} ${n5}`;
}

/** WGS84 → grid key + OS ref, or null outside BNG extent. */
export function wgs84ToGrid3(
  lng: number,
  lat: number,
): { key: string; ref: string; easting: number; northing: number } | null {
  const { easting, northing } = wgs84ToBng(lng, lat);
  if (!inBngExtent(easting, northing)) return null;
  const sw = floorToGrid3(easting, northing);
  return {
    key: grid3Key(sw.easting, sw.northing),
    ref: grid3OsRef(sw.easting, sw.northing),
    easting: sw.easting,
    northing: sw.northing,
  };
}

/** Four WGS84 corners of a 3 m square (SW → SE → NE → NW → SW ring). */
export function grid3CornersWgs(
  easting: number,
  northing: number,
): [WgsPoint, WgsPoint, WgsPoint, WgsPoint] {
  const sw = floorToGrid3(easting, northing);
  const e0 = sw.easting;
  const n0 = sw.northing;
  return [
    bngToWgs84(e0, n0),
    bngToWgs84(e0 + GRID3_METRES, n0),
    bngToWgs84(e0 + GRID3_METRES, n0 + GRID3_METRES),
    bngToWgs84(e0, n0 + GRID3_METRES),
  ];
}

/** Card / row-6 copy for a selected square. */
export function grid3Row6Text(ref: string): string {
  return `Grid square ${ref} (a map grid, not a property)`;
}

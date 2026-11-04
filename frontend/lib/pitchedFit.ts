/**
 * OPENING-3D-FRAMING (UX picks 4 Nov 2026): fit a lng/lat box on screen with
 * the opening tilt applied. MapLibre's cameraForBounds/fitBounds size the box
 * as if the map were flat, so at pitch 55-60 the far (north) edge shrinks and
 * the near (south) edge spills past the padding. This corrects the flat fit by
 * projecting the box corners at the real pitch and refitting.
 * DEFAULT-3D-VIEW pitch/bearing values are unchanged; only zoom/centre move.
 */
import { validateBearingParam, validatePitchParam } from "./default3dView";

export type FitPadding = { top: number; bottom: number; left: number; right: number };
export type LngLatBox = [[number, number], [number, number]];

/** The slice of a MapLibre map this helper needs (keeps it testable). */
export interface PitchedFitMap {
  fitBounds(bounds: LngLatBox, options: Record<string, unknown>): unknown;
  jumpTo(options: { center?: [number, number]; zoom?: number }): unknown;
  project(lngLat: [number, number]): { x: number; y: number };
  unproject(point: [number, number]): { lng: number; lat: number };
  getZoom(): number;
  getCenter(): { lng: number; lat: number };
  getContainer(): { clientWidth: number; clientHeight: number };
}

/** Recentre passes per zoom tried. */
export const PITCHED_FIT_CENTRE_STEPS = 10;
/** Bisection passes on zoom (range / 2^18 is far below a pixel). */
export const PITCHED_FIT_BISECT_STEPS = 18;
/** How far below the flat-fit zoom to search. */
export const PITCHED_FIT_ZOOM_RANGE = 3;
/** Stop when the box is within this many px of its target on every side. */
export const PITCHED_FIT_TOLERANCE_PX = 1;

const ERR = "OPENING-3D-FRAMING:";

function finite(n: unknown): n is number {
  return typeof n === "number" && Number.isFinite(n);
}

/** Refuse anything that is not a real, non-inverted lng/lat box. */
export function validateFitBox(box: unknown): LngLatBox {
  if (!Array.isArray(box) || box.length !== 2) {
    throw new Error(`${ERR} bounds must be [[west, south], [east, north]]`);
  }
  const [sw, ne] = box as unknown[];
  if (!Array.isArray(sw) || !Array.isArray(ne) || sw.length !== 2 || ne.length !== 2) {
    throw new Error(`${ERR} bounds must be [[west, south], [east, north]]`);
  }
  const [w, s] = sw as unknown[];
  const [e, n] = ne as unknown[];
  if (![w, s, e, n].every(finite)) {
    throw new Error(`${ERR} bounds must be finite numbers`);
  }
  const W = w as number, S = s as number, E = e as number, N = n as number;
  if (W < -180 || E > 180 || S < -85 || N > 85 || W >= E || S >= N) {
    throw new Error(`${ERR} bounds must be a non-empty box with west < east and south < north`);
  }
  return [[W, S], [E, N]];
}

export function validateFitPadding(p: unknown): FitPadding {
  if (!p || typeof p !== "object") throw new Error(`${ERR} padding must be an object`);
  const o = p as Record<string, unknown>;
  for (const k of ["top", "bottom", "left", "right"]) {
    const v = o[k];
    if (!finite(v) || v < 0) throw new Error(`${ERR} padding.${k} must be a finite number >= 0`);
  }
  return { top: o.top as number, bottom: o.bottom as number, left: o.left as number, right: o.right as number };
}

/** Screen box of the four corners of a lng/lat box. */
export function projectedBox(map: PitchedFitMap, box: LngLatBox) {
  const [[w, s], [e, n]] = box;
  const pts = [map.project([w, s]), map.project([e, s]), map.project([e, n]), map.project([w, n])];
  if (!pts.every((p) => finite(p.x) && finite(p.y))) {
    throw new Error(`${ERR} a corner could not be projected`);
  }
  return {
    left: Math.min(...pts.map((p) => p.x)),
    right: Math.max(...pts.map((p) => p.x)),
    top: Math.min(...pts.map((p) => p.y)),
    bottom: Math.max(...pts.map((p) => p.y)),
  };
}

/**
 * Fit `bounds` inside the padded viewport at `pitch`/`bearing`, without
 * animation. Returns the number of correction steps taken.
 */
export function fitBoundsPitched(
  map: PitchedFitMap,
  bounds: unknown,
  opts: { padding: unknown; maxZoom: unknown; minZoom?: unknown; pitch: unknown; bearing: unknown },
): number {
  const box = validateFitBox(bounds);
  const padding = validateFitPadding(opts.padding);
  const pitch = validatePitchParam(opts.pitch);
  const bearing = validateBearingParam(opts.bearing);
  if (!finite(opts.maxZoom)) throw new Error(`${ERR} maxZoom must be a finite number`);
  const maxZoom = opts.maxZoom;
  const minZoom = opts.minZoom ?? -Infinity;
  if (typeof minZoom !== "number" || Number.isNaN(minZoom) || minZoom > maxZoom) {
    throw new Error(`${ERR} minZoom must be a number <= maxZoom`);
  }
  const { clientWidth: cw, clientHeight: ch } = map.getContainer();
  const availW = cw - padding.left - padding.right;
  const availH = ch - padding.top - padding.bottom;
  if (!(availW > 0 && availH > 0)) {
    throw new Error(`${ERR} padding leaves no room on screen`);
  }
  // Flat fit first: right pitch/bearing, approximately right zoom/centre.
  map.fitBounds(box, { padding, animate: false, maxZoom, pitch, bearing });
  const flatZoom = map.getZoom();
  let steps = 0;
  const centreAndCheck = (zoom: number): boolean => {
    map.jumpTo({ zoom });
    let b = projectedBox(map, box);
    for (let k = 0; k < PITCHED_FIT_CENTRE_STEPS; k++) {
      steps += 1;
      // Move the box centre to the centre of the padded area. The camera
      // centre sits at the map's own padded centre, not always the container
      // centre, so shift relative to where the centre projects.
      const dx = padding.left + availW / 2 - (b.left + b.right) / 2;
      const dy = padding.top + availH / 2 - (b.top + b.bottom) / 2;
      if (Math.abs(dx) <= PITCHED_FIT_TOLERANCE_PX / 2 && Math.abs(dy) <= PITCHED_FIT_TOLERANCE_PX / 2) break;
      const now = map.getCenter();
      const at = map.project([now.lng, now.lat]);
      const c = map.unproject([at.x - dx, at.y - dy]);
      map.jumpTo({ center: [c.lng, c.lat] });
      b = projectedBox(map, box);
    }
    // The box is centred in the padded area now, so it fits when its
    // width and height do.
    return (
      b.right - b.left <= availW + PITCHED_FIT_TOLERANCE_PX &&
      b.bottom - b.top <= availH + PITCHED_FIT_TOLERANCE_PX
    );
  };
  // Largest zoom (<= maxZoom) at which the tilted box still fits: bisection.
  let hi = maxZoom;
  if (centreAndCheck(hi)) return steps;
  let lo = Math.max(flatZoom - PITCHED_FIT_ZOOM_RANGE, minZoom);
  if (!centreAndCheck(lo)) {
    // Floor reached (e.g. layer minzoom on a phone): stay centred at the floor.
    if (lo === minZoom) return steps;
    throw new Error(`${ERR} bounds do not fit even when zoomed out`);
  }
  for (let k = 0; k < PITCHED_FIT_BISECT_STEPS; k++) {
    const mid = (lo + hi) / 2;
    if (centreAndCheck(mid)) lo = mid;
    else hi = mid;
  }
  centreAndCheck(lo);
  return steps;
}

/** Opening national frame (same box the flat fit used before). */
export const SCOTLAND_FIT_BOUNDS: LngLatBox = [
  [-8.05, 54.48],
  [-0.55, 60.88],
];

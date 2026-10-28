/**
 * DEFAULT-3D-VIEW (scot-land.md:167-168):
 * Tilted 3D opening camera looking north over Scotland, MapLibre sky (no globe),
 * 2D/3D circular toggle helpers, and strict pitch/bearing validators.
 */

export const DEFAULT_3D_PITCH_DESKTOP = 60;
export const DEFAULT_3D_PITCH_MOBILE = 55;
export const DEFAULT_3D_BEARING = 0;
export const DEFAULT_3D_MOBILE_MAX_WIDTH = 900;

export const VIEW_3D_TOGGLE_ARIA_LABEL_3D = "3D view";
export const VIEW_3D_TOGGLE_ARIA_LABEL_2D = "2D flat view";

/**
 * MapLibre sky specification for tilted 3D views (atmosphere/horizon, no globe).
 */
export const SCOTLAND_SKY_SPEC = {
  "sky-color": "#dbeafe",
  "horizon-color": "#f8fafc",
  "fog-color": "#f1f5f9",
  "sky-horizon-blend": 0.5,
  "horizon-fog-blend": 0.5,
  "fog-ground-blend": 0.25,
  "atmosphere-blend": 0.7,
} as const;

/**
 * Default opening pitch: 0 when reduced motion is active, ~55° on phone
 * (`viewportWidth <= 900`), and ~60° on desktop.
 */
export function defaultOpeningPitch(
  viewportWidth: unknown,
  reducedMotion: unknown = false,
): number {
  if (
    typeof viewportWidth !== "number" ||
    !Number.isFinite(viewportWidth) ||
    viewportWidth <= 0
  ) {
    throw new Error("DEFAULT-3D: viewportWidth must be a positive finite number");
  }
  if (typeof reducedMotion !== "boolean") {
    throw new Error("DEFAULT-3D: reducedMotion must be a boolean");
  }
  if (reducedMotion) return 0;
  return viewportWidth <= DEFAULT_3D_MOBILE_MAX_WIDTH
    ? DEFAULT_3D_PITCH_MOBILE
    : DEFAULT_3D_PITCH_DESKTOP;
}

/**
 * Validate a pitch number or numeric string in `[0, 60]`.
 */
export function validatePitchParam(raw: unknown): number {
  if (typeof raw === "boolean" || raw === null || raw === undefined) {
    throw new Error("DEFAULT-3D: pitch must be a finite number in [0, 60]");
  }
  if (typeof raw === "string") {
    if (!raw.trim()) {
      throw new Error("DEFAULT-3D: pitch must be a finite number in [0, 60]");
    }
    const n = Number(raw.trim());
    if (!Number.isFinite(n) || n < 0 || n > 60) {
      throw new Error("DEFAULT-3D: pitch must be a finite number in [0, 60]");
    }
    return Math.round(n * 10) / 10;
  }
  if (typeof raw === "number") {
    if (!Number.isFinite(raw) || raw < 0 || raw > 60) {
      throw new Error("DEFAULT-3D: pitch must be a finite number in [0, 60]");
    }
    return Math.round(raw * 10) / 10;
  }
  throw new Error("DEFAULT-3D: pitch must be a finite number in [0, 60]");
}

/**
 * Validate a bearing number or numeric string in `[-180, 180]`.
 */
export function validateBearingParam(raw: unknown): number {
  if (typeof raw === "boolean" || raw === null || raw === undefined) {
    throw new Error("DEFAULT-3D: bearing must be a finite number in [-180, 180]");
  }
  if (typeof raw === "string") {
    if (!raw.trim()) {
      throw new Error(
        "DEFAULT-3D: bearing must be a finite number in [-180, 180]",
      );
    }
    const n = Number(raw.trim());
    if (!Number.isFinite(n) || n < -180 || n > 180) {
      throw new Error(
        "DEFAULT-3D: bearing must be a finite number in [-180, 180]",
      );
    }
    const r = Math.round(n * 10) / 10;
    return Object.is(r, -0) ? 0 : r;
  }
  if (typeof raw === "number") {
    if (!Number.isFinite(raw) || raw < -180 || raw > 180) {
      throw new Error(
        "DEFAULT-3D: bearing must be a finite number in [-180, 180]",
      );
    }
    const r = Math.round(raw * 10) / 10;
    return Object.is(r, -0) ? 0 : r;
  }
  throw new Error("DEFAULT-3D: bearing must be a finite number in [-180, 180]");
}

export function is3dPitchActive(pitch: unknown): boolean {
  const valid = validatePitchParam(pitch);
  return valid > 0;
}

export function nextTogglePitch(
  currentPitch: unknown,
  viewportWidth: unknown,
): { pitch: number; bearing: number } {
  const active = is3dPitchActive(currentPitch);
  if (active) {
    return { pitch: 0, bearing: 0 };
  }
  return {
    pitch: defaultOpeningPitch(viewportWidth, false),
    bearing: DEFAULT_3D_BEARING,
  };
}

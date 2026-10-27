/**
 * MAP-VISION-1 slice 1a (MV-04, MV-05, MV-06, MV-09, MV-11, MV-20):
 * Shared colour tokens, DZ fill opacity dimming, selected/hover outline paint,
 * supporting-layer shape/dash tokens, and reduced-motion camera helper.
 */

export const MV_SEQ_TOKENS = {
  "seq-0": "#BDBDBD",
  "seq-1": "#FDE725",
  "seq-2": "#7AD151",
  "seq-3": "#22A884",
  "seq-4": "#2A788E",
  "seq-5": "#414487",
  "seq-6": "#440154",
} as const;

export const MV_CAT_TOKENS = {
  "cat-1": "#E69F00",
  "cat-2": "#56B4E9",
  "cat-3": "#009E73",
  "cat-4": "#0072B2",
  "cat-5": "#D55E00",
  "cat-6": "#CC79A7",
} as const;

export const MV_INK = "#1A1A1A";
export const MV_HALO = "#FFFFFF";
export const MV_DZ_FILL_OPACITY_BASE = 0.55;
export const MV_DZ_FILL_OPACITY_DIMMED = 0.33; // 60% of 0.55 when supporting layer is on (MV-05)

export type MvSeqTokenId = keyof typeof MV_SEQ_TOKENS;
export type MvCatTokenId = keyof typeof MV_CAT_TOKENS;

export type SupportingStrokeStyle = {
  token: MvCatTokenId;
  color: string;
  dasharray: readonly number[];
  lineWidth: number;
};

/**
 * MV-11: Supporting layers get an Okabe-Ito categorical colour token AND a
 * distinct dash pattern so colour is never the only visual cue.
 */
export const MV_SUPPORTING_STROKE_STYLES: Readonly<
  Record<string, SupportingStrokeStyle>
> = {
  "oil-fields": {
    token: "cat-5",
    color: MV_CAT_TOKENS["cat-5"],
    dasharray: [4, 2],
    lineWidth: 1.8,
  },
  pipelines: {
    token: "cat-1",
    color: MV_CAT_TOKENS["cat-1"],
    dasharray: [6, 2, 1.5, 2],
    lineWidth: 1.6,
  },
  "seabed-leases": {
    token: "cat-4",
    color: MV_CAT_TOKENS["cat-4"],
    dasharray: [3, 2],
    lineWidth: 1.6,
  },
  "wind-leases": {
    token: "cat-2",
    color: MV_CAT_TOKENS["cat-2"],
    dasharray: [5, 2],
    lineWidth: 1.6,
  },
  "wave-tidal": {
    token: "cat-3",
    color: MV_CAT_TOKENS["cat-3"],
    dasharray: [2, 2],
    lineWidth: 1.6,
  },
  designations: {
    token: "cat-3",
    color: MV_CAT_TOKENS["cat-3"],
    dasharray: [4, 1.5, 1, 1.5],
    lineWidth: 1.6,
  },
  "crown-leases": {
    token: "cat-4",
    color: MV_CAT_TOKENS["cat-4"],
    dasharray: [5, 2],
    lineWidth: 1.6,
  },
  vdl: {
    token: "cat-6",
    color: MV_CAT_TOKENS["cat-6"],
    dasharray: [2.5, 1.5],
    lineWidth: 1.6,
  },
};

export function resolveSeqToken(id: unknown): string {
  if (typeof id !== "string" || !(id in MV_SEQ_TOKENS)) {
    throw new Error(`MAP-VISION: unknown seq token ${String(id)}`);
  }
  return MV_SEQ_TOKENS[id as MvSeqTokenId];
}

export function resolveCatToken(id: unknown): string {
  if (typeof id !== "string" || !(id in MV_CAT_TOKENS)) {
    throw new Error(`MAP-VISION: unknown cat token ${String(id)}`);
  }
  return MV_CAT_TOKENS[id as MvCatTokenId];
}

export function resolveSupportingStrokeStyle(
  layerId: unknown,
): SupportingStrokeStyle {
  if (typeof layerId !== "string" || !(layerId in MV_SUPPORTING_STROKE_STYLES)) {
    throw new Error(
      `MAP-VISION: unknown supporting layer ${String(layerId)}`,
    );
  }
  return MV_SUPPORTING_STROKE_STYLES[layerId]!;
}

/**
 * MV-04: Validate that a supporting layer kind is outline/line/point only,
 * never a second polygon fill competing with the DZ main measure.
 */
export function assertSupportingLayerNotFill(
  layerId: unknown,
  kind: unknown,
): void {
  if (typeof layerId !== "string" || !layerId.trim()) {
    throw new Error("MAP-VISION: layerId must be a non-empty string");
  }
  if (kind !== "line" && kind !== "circle" && kind !== "outline") {
    throw new Error(
      `MAP-VISION: supporting layer '${layerId}' must not use kind '${String(kind)}'`,
    );
  }
}

/**
 * MV-05: Compute the DZ2022 fill-opacity MapLibre expression.
 * When any supporting layer is active (`supportingActive === true`), the
 * z5–z14 plateau dims to 60% of 0.55 (`0.33`).
 */
export function buildDzFillOpacityExpression(
  supportingActive: unknown,
): unknown[] {
  if (typeof supportingActive !== "boolean") {
    throw new Error("MAP-VISION: supportingActive must be a boolean");
  }
  const plateau = supportingActive
    ? MV_DZ_FILL_OPACITY_DIMMED
    : MV_DZ_FILL_OPACITY_BASE;
  const highZoom = supportingActive ? 0.24 : 0.4;
  return [
    "interpolate",
    ["linear"],
    ["zoom"],
    4.5,
    0,
    5,
    plateau,
    14,
    plateau,
    15,
    highZoom,
  ];
}

/**
 * MV-05: Determine whether any supporting overlay layer is currently active
 * above the DZ fill (excluding base framing outlines `councils` and `data_zones`).
 */
export function hasSupportingOverlayActive(
  activeLayerIds: unknown,
): boolean {
  if (!Array.isArray(activeLayerIds)) {
    throw new Error("MAP-VISION: activeLayerIds must be an array of strings");
  }
  const baseFraming = new Set(["councils", "data_zones", "dz2022", "1"]);
  for (const id of activeLayerIds) {
    if (typeof id !== "string" || !id.trim()) {
      throw new Error("MAP-VISION: activeLayerIds must be an array of strings");
    }
    if (!baseFraming.has(id.trim())) {
      return true;
    }
  }
  return false;
}

/**
 * MV-06: Build MapLibre paint specs for the selected Data Zone (3 px dark
 * `#1A1A1A` outline + `#FFFFFF` halo) and desktop hover (1.5 px outline).
 */
export function buildSelectedZonePaint(
  selectedCode: unknown,
  hoveredCode: unknown,
): {
  haloFilter: unknown[];
  haloPaint: Record<string, unknown>;
  outlineFilter: unknown[];
  outlinePaint: Record<string, unknown>;
  hoverFilter: unknown[];
  hoverPaint: Record<string, unknown>;
} {
  if (
    selectedCode !== null &&
    (typeof selectedCode !== "string" || !selectedCode.trim())
  ) {
    throw new Error(
      "MAP-VISION: selectedCode must be a non-empty string or null",
    );
  }
  if (
    hoveredCode !== null &&
    (typeof hoveredCode !== "string" || !hoveredCode.trim())
  ) {
    throw new Error(
      "MAP-VISION: hoveredCode must be a non-empty string or null",
    );
  }
  const sel = selectedCode ? selectedCode.trim() : "";
  const hov = hoveredCode && hoveredCode.trim() !== sel ? hoveredCode.trim() : "";
  return {
    haloFilter: ["==", ["coalesce", ["get", "feature_id"], ["get", "code"], ""], sel],
    haloPaint: {
      "line-color": MV_HALO,
      "line-width": 5,
      "line-opacity": sel ? 0.95 : 0,
    },
    outlineFilter: ["==", ["coalesce", ["get", "feature_id"], ["get", "code"], ""], sel],
    outlinePaint: {
      "line-color": MV_INK,
      "line-width": 3,
      "line-opacity": sel ? 1 : 0,
    },
    hoverFilter: ["==", ["coalesce", ["get", "feature_id"], ["get", "code"], ""], hov],
    hoverPaint: {
      "line-color": MV_INK,
      "line-width": 1.5,
      "line-opacity": hov ? 0.85 : 0,
    },
  };
}

/**
 * MV-20: Detect `prefers-reduced-motion: reduce` and choose `"jumpTo"` instead
 * of `"flyTo"` / animated camera transitions.
 */
export function prefersReducedMotion(win?: unknown): boolean {
  const target =
    win !== undefined
      ? win
      : typeof window !== "undefined"
        ? window
        : null;
  if (target === null) return false;
  if (typeof target !== "object") {
    throw new Error("MAP-VISION: win must be a Window object or null");
  }
  const mm = (target as { matchMedia?: unknown }).matchMedia;
  if (typeof mm !== "function") return false;
  const res = (
    mm as (q: string) => { matches?: unknown } | null | undefined
  ).call(target, "(prefers-reduced-motion: reduce)");
  return Boolean(res && res.matches === true);
}

export function selectCameraMotionMethod(
  reducedMotion: unknown,
): "jumpTo" | "flyTo" {
  if (typeof reducedMotion !== "boolean") {
    throw new Error("MAP-VISION: reducedMotion must be a boolean");
  }
  return reducedMotion ? "jumpTo" : "flyTo";
}

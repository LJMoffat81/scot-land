/**
 * SW-045 — map legend follows the active layer only.
 * Land worth uses a colour-blind-safe cividis ramp (no £ in the legend).
 */

import {
  POP_DENSITY_LEGEND_BLURB,
  POP_DENSITY_LEGEND_SOURCE,
  POP_DENSITY_LEGEND_TITLE,
  POP_DENSITY_ZOOM_HINT,
  publicContextMetric,
} from "@/lib/mapColourRamps";
import {
  rangeLegendFromStops,
  type RangeLegendStop,
} from "@/lib/mapLicenceCredits";

/** off = nothing drawn; zoom-hint = layer active but colours not at this zoom. */
export type ActiveLegendMode = "off" | "zoom-hint" | "bands";

/** Exact visitor wording (UX-10 Map / SW-045). */
export const LAND_WORTH_LEGEND_TITLE =
  "What the land is worth each year: lower to higher";

/** Exact confidence line under the Land worth ramp (UX-10 Map / SW-045). */
export const LAND_WORTH_LEGEND_PALER = "Paler = less sure";

/**
 * Colour-blind-safe cividis samples (matplotlib), lower → higher.
 * Used for Land worth legend bands only — never labelled with £.
 */
export const LAND_WORTH_CIVIDIS: readonly string[] = [
  "#00224e",
  "#123570",
  "#3b496c",
  "#575d6d",
  "#707173",
  "#8a8678",
  "#a59c74",
  "#c3b369",
  "#e1cc55",
  "#fee838",
] as const;

/** Vacant / derelict site-type fills — keep in sync with ScotlandMap VDL_FILL. */
export const VDL_LEGEND_SWATCHES: ReadonlyArray<{
  label: string;
  color: string;
}> = [
  { label: "Vacant Land", color: "#e8a317" },
  { label: "Vacant Land and Buildings", color: "#c45c26" },
  { label: "Derelict", color: "#7a2e00" },
];

/** Housing land audit fill — keep in sync with ScotlandMap HLA_FILL. */
export const HLA_LEGEND_SWATCH = {
  label: "Housing land audit",
  color: "#7b5ea7",
} as const;

export const VDL_LEGEND_TITLE = "Vacant and derelict land";
export const HLA_LEGEND_TITLE = "Housing land audit";

/** Layer ids that drive the range / categorical legend (drawer toggle ids). */
export const LEGEND_LAYER_IDS = ["1", "data_zones", "vdl", "hla"] as const;
export type LegendLayerId = (typeof LEGEND_LAYER_IDS)[number];

export function isLegendLayerId(id: string): id is LegendLayerId {
  return (LEGEND_LAYER_IDS as readonly string[]).includes(id);
}

export type ActiveLegendView = {
  /** Drawer / catalog id that owns this legend, or "density" for the default ramp. */
  layerId: LegendLayerId | "density";
  title: string;
  blurb?: string;
  /** Confidence / certainty line (Land worth only). */
  paler?: string;
  ranges: RangeLegendStop[];
  showNoData: boolean;
  mode: ActiveLegendMode;
  zoomHint?: string;
  source?: string | null;
};

/** Build Land worth bands from cividis — labels carry lower/higher only (no £). */
export function landWorthLegendRanges(): RangeLegendStop[] {
  const colors = LAND_WORTH_CIVIDIS;
  return colors.map((color, index) => {
    if (index === 0) {
      return { from: "Lower", to: "", color, label: "Lower" };
    }
    if (index === colors.length - 1) {
      return { from: "Higher", to: "", color, label: "Higher" };
    }
    return { from: "", to: "", color, label: "·" };
  });
}

function categoricalRanges(
  rows: ReadonlyArray<{ label: string; color: string }>,
): RangeLegendStop[] {
  return rows.map((row) => ({
    from: row.label,
    to: "",
    color: row.color,
    label: row.label,
  }));
}

/**
 * Pick which layer the legend follows.
 * Prefer the most recently activated legend-capable layer that is still on;
 * otherwise fall back to density (default public reference ramp).
 */
export function resolveLegendFocusId(
  enabled: Record<string, boolean>,
  preferredId: string | null,
): LegendLayerId | "density" {
  if (preferredId && isLegendLayerId(preferredId) && enabled[preferredId]) {
    return preferredId;
  }
  // Stable fallback order among currently-on layers (Land first).
  for (const id of LEGEND_LAYER_IDS) {
    if (enabled[id]) return id;
  }
  return "density";
}

/**
 * Build the single active-layer legend view (SW-045: one layer's bands only).
 */
export function buildActiveLegendView(opts: {
  focusId: LegendLayerId | "density";
  mapZoom: number;
  densityColoursMinZoom: number;
  /** Data zones on, or still auto-enabling at neighbourhood zoom. */
  densityDrawable: boolean;
}): ActiveLegendView {
  const { focusId, mapZoom, densityColoursMinZoom, densityDrawable } = opts;

  if (focusId === "1") {
    return {
      layerId: "1",
      title: LAND_WORTH_LEGEND_TITLE,
      paler: LAND_WORTH_LEGEND_PALER,
      ranges: landWorthLegendRanges(),
      showNoData: true,
      mode: "bands",
      source: null,
    };
  }

  if (focusId === "vdl") {
    return {
      layerId: "vdl",
      title: VDL_LEGEND_TITLE,
      ranges: categoricalRanges(VDL_LEGEND_SWATCHES),
      showNoData: false,
      mode: mapZoom < 8 ? "zoom-hint" : "bands",
      zoomHint: "Zoom in to see colours",
      source: null,
    };
  }

  if (focusId === "hla") {
    return {
      layerId: "hla",
      title: HLA_LEGEND_TITLE,
      ranges: categoricalRanges([HLA_LEGEND_SWATCH]),
      showNoData: false,
      mode: mapZoom < 8 ? "zoom-hint" : "bands",
      zoomHint: "Zoom in to see colours",
      source: null,
    };
  }

  // Default / data_zones → population density (SW-022 wording unchanged).
  const metric = publicContextMetric();
  const legend = rangeLegendFromStops(metric.stops, {
    metricId: metric.id,
    unit: metric.unit,
  });
  let mode: ActiveLegendMode = "bands";
  if (mapZoom < densityColoursMinZoom) {
    mode = "zoom-hint";
  } else if (!densityDrawable) {
    mode = "off";
  }
  return {
    layerId: focusId === "data_zones" ? "data_zones" : "density",
    title: POP_DENSITY_LEGEND_TITLE,
    blurb: POP_DENSITY_LEGEND_BLURB,
    ranges: legend.ranges,
    showNoData: true,
    mode,
    zoomHint: POP_DENSITY_ZOOM_HINT,
    source: POP_DENSITY_LEGEND_SOURCE,
  };
}

/**
 * Detect a newly enabled legend-capable layer (for focus tracking).
 * Returns null when nothing new turned on.
 */
export function newlyEnabledLegendLayer(
  prev: Record<string, boolean>,
  next: Record<string, boolean>,
): LegendLayerId | null {
  for (const id of LEGEND_LAYER_IDS) {
    if (next[id] && !prev[id]) return id;
  }
  return null;
}

/** True when the preferred legend layer is no longer on. */
export function isLegendLayerOff(
  preferredId: string,
  enabled: Record<string, boolean>,
): boolean {
  return !enabled[preferredId];
}

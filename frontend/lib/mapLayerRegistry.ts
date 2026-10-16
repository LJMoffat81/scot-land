/**
 * MAP-CARDS live map-layer registry — single source for Layers panel rows,
 * inline legends, and zoom gates. Paint toggle ids stay stable for ScotlandMap.
 *
 * Addendum A1: every entry has numeric minzoom, maxzoom, and non-empty group.
 */

import { DZ2022_EXTRACTION_YEAR } from "./dz2022ExtractionYear.mjs";
import { RENT_GROUP_NAME } from "./rentGroupNames.mjs";

/** Colour-blind-safe cividis samples — keep in sync with mapActiveLegend. */
const LAND_WORTH_CIVIDIS: readonly string[] = [
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
const VDL_LEGEND_SWATCHES: ReadonlyArray<{ label: string; color: string }> = [
  { label: "Vacant Land", color: "#e8a317" },
  { label: "Vacant Land and Buildings", color: "#c45c26" },
  { label: "Derelict", color: "#7a2e00" },
];

/** Live Layers panel groups (accordion). */
export type MapLayerGroupKey = "land" | "resources" | "nature" | "places";

export type MapLayerEvidenceTag = "market" | "proxy" | "shadow";

export type MapLayerLegendClass = {
  /** Visitor label (e.g. Lower, Higher, Vacant Land, No figure here). */
  label: string;
  color: string;
  /** Diagonal hatch key row (certainty). */
  striped?: boolean;
};

export type MapLayerRegistryEntry = {
  /** Stable paint / URL toggle id. */
  id: string;
  /** Optional URL aliases (e.g. agr → 1). */
  aliases?: readonly string[];
  group: MapLayerGroupKey;
  label: string;
  minzoom: number;
  maxzoom: number;
  /** "Source · year" caption under the inline legend (not a licence line). */
  sourceCaption: string;
  /** Legend unit, e.g. "£/year" when GBP-LIVE labels are used; omit for ramp-only. */
  legendUnit?: string;
  /** Classed legend rows (ramp / categorical / certainty keys). */
  classes: readonly MapLayerLegendClass[];
  /** When true, legend shows a Non-commercial tag. */
  nonCommercial?: boolean;
  /** Evidence chip inside the inline legend only (not on the row). */
  chip?: MapLayerEvidenceTag | null;
  /** Initial map rest state — drawer open never forces this on. */
  defaultOn?: boolean;
  /**
   * When true, the row is listed but paint may be a no-op / zoom-gate only
   * until ScotlandMap wires a source.
   */
  paintPending?: boolean;
  /** Accessible row description (e.g. grid3 “Shows when you zoom right in”). */
  subline?: string;
  /** Inline legend zoom gate copy when gated (defaults to LAYER_ZOOM_HINT). */
  zoomHint?: string;
};

export const MAP_LAYER_GROUP_ORDER: MapLayerGroupKey[] = [
  "land",
  "resources",
  "nature",
  "places",
];

export const PLACES_AND_BOUNDARIES_LABEL = "Places and boundaries";

export function mapLayerGroupLabel(group: MapLayerGroupKey): string {
  switch (group) {
    case "land":
      return RENT_GROUP_NAME.land;
    case "resources":
      return RENT_GROUP_NAME.resources;
    case "nature":
      return RENT_GROUP_NAME.nature;
    case "places":
      return PLACES_AND_BOUNDARIES_LABEL;
    default: {
      const _exhaustive: never = group;
      return _exhaustive;
    }
  }
}

/** Five cividis samples for classed AGR / value ramps (GIS 9). */
export function cividisLegendClasses(
  labels: readonly [string, string, string, string, string] = [
    "Lower",
    "",
    "",
    "",
    "Higher",
  ],
): MapLayerLegendClass[] {
  const colors = LAND_WORTH_CIVIDIS;
  const picks = [0, 2, 4, 7, colors.length - 1] as const;
  return picks.map((idx, i) => ({
    label: labels[i] || "·",
    color: colors[idx]!,
  }));
}

const AGR_CLASSES: MapLayerLegendClass[] = [
  ...cividisLegendClasses(["Lower", "·", "·", "·", "Higher"]),
  { label: "Striped = less sure", color: "#7d7c78", striped: true },
  { label: "No figure here", color: "#bbbbbb" },
];

const VDL_CLASSES: MapLayerLegendClass[] = VDL_LEGEND_SWATCHES.map((row) => ({
  label: row.label,
  color: row.color,
}));

const HLA_CLASSES: MapLayerLegendClass[] = [
  { label: "Housing land audit", color: "#7b5ea7" },
];

const OUTLINE_CLASSES: MapLayerLegendClass[] = [
  { label: "Boundary lines", color: "#334155" },
];

/**
 * Live Layers switches only — no Coming soon / Coming later rows.
 * Ids match ScotlandMap paint toggles where they already exist.
 */
export const MAP_LAYER_REGISTRY: readonly MapLayerRegistryEntry[] = [
  {
    id: "1",
    aliases: ["agr"],
    group: "land",
    label: "Annual Ground Rent",
    minzoom: 5,
    maxzoom: 19,
    sourceCaption: "Scot-LAND model · 2023",
    legendUnit: "£/year",
    classes: AGR_CLASSES,
    chip: "proxy",
    defaultOn: false,
  },
  {
    id: "access_services",
    group: "land",
    label: "Why it's valuable: access to services (2020 data)",
    minzoom: 8,
    maxzoom: 19,
    sourceCaption: "Scottish Government · 2020",
    classes: cividisLegendClasses(),
    chip: "proxy",
    defaultOn: false,
    paintPending: true,
  },
  {
    id: "vdl",
    group: "land",
    label: "Vacant and derelict land",
    minzoom: 8,
    maxzoom: 19,
    sourceCaption: "Scottish Government · SVDLS",
    classes: VDL_CLASSES,
    chip: "proxy",
    defaultOn: false,
  },
  {
    id: "grid3",
    group: "land",
    label: "3 m grid",
    minzoom: 17,
    maxzoom: 20,
    // Device-drawn overlay — not an OS/SG data product; no Ordnance Survey credit.
    sourceCaption: "Scot-LAND · device-drawn",
    classes: [{ label: "3 m grid", color: "#0b2340" }],
    defaultOn: false,
    subline: "Shows when you zoom right in",
    zoomHint: "Zoom in to see the grid",
  },
  {
    id: "hla",
    group: "land",
    label: "Housing land audit",
    minzoom: 8,
    maxzoom: 19,
    sourceCaption: "Spatial Hub · Housing land supply",
    classes: HLA_CLASSES,
    chip: "proxy",
    defaultOn: false,
  },
  {
    id: "3",
    group: "resources",
    label: "Onshore wind and hydro",
    minzoom: 6,
    maxzoom: 19,
    sourceCaption: "DESNZ REPD · open data",
    classes: [{ label: "Wind and hydro sites", color: "#0d9488" }],
    chip: "proxy",
    defaultOn: false,
  },
  {
    id: "4",
    group: "resources",
    label: "Seabed and foreshore",
    minzoom: 5,
    maxzoom: 19,
    sourceCaption: "Crown Estate Scotland · open data",
    classes: [{ label: "Seabed and foreshore leases", color: "#0369a1" }],
    chip: "market",
    defaultOn: false,
  },
  {
    id: "9",
    group: "resources",
    label: "Oil and gas",
    minzoom: 5,
    maxzoom: 19,
    sourceCaption: "North Sea Transition Authority · open data",
    classes: [{ label: "Oil and gas fields", color: "#57534e" }],
    nonCommercial: true,
    defaultOn: false,
  },
  {
    id: "8",
    group: "nature",
    label: "Peat and soil carbon",
    minzoom: 6,
    maxzoom: 19,
    sourceCaption: "NatureScot / soils research · open data",
    classes: [{ label: "Peat and soil carbon", color: "#78350f" }],
    nonCommercial: true,
    chip: "shadow",
    defaultOn: false,
  },
  {
    id: "designations",
    group: "nature",
    label: "Protected nature sites",
    minzoom: 6,
    maxzoom: 19,
    sourceCaption: "NatureScot · open data",
    classes: [{ label: "Protected sites", color: "#15803d" }],
    defaultOn: false,
  },
  {
    id: "flood",
    group: "nature",
    label: "Flood",
    minzoom: 7,
    maxzoom: 19,
    sourceCaption: "SEPA Flood Maps · open data",
    classes: [{ label: "Flood risk", color: "#2563eb" }],
    defaultOn: false,
  },
  {
    id: "crofting",
    group: "nature",
    label: "Crofting / common grazings",
    minzoom: 6,
    maxzoom: 19,
    sourceCaption: "Crofting Commission · open lists",
    classes: [{ label: "Crofting areas", color: "#a16207" }],
    defaultOn: false,
  },
  {
    id: "councils",
    group: "places",
    label: "Council areas",
    minzoom: 5,
    maxzoom: 19,
    sourceCaption: "Scottish Government · council boundaries",
    classes: OUTLINE_CLASSES,
    defaultOn: true,
  },
  {
    id: "data_zones",
    group: "places",
    label: "Neighbourhood lines",
    minzoom: 8,
    maxzoom: 19,
    sourceCaption: `Scottish Government · ${DZ2022_EXTRACTION_YEAR}`,
    classes: OUTLINE_CLASSES,
    defaultOn: false,
  },
];

/** Canonical id → entry. */
export const MAP_LAYER_BY_ID: ReadonlyMap<string, MapLayerRegistryEntry> =
  new Map(MAP_LAYER_REGISTRY.map((entry) => [entry.id, entry]));

/** Alias and canonical id → canonical id. */
export const MAP_LAYER_ID_ALIASES: Readonly<Record<string, string>> =
  Object.freeze(
    Object.fromEntries(
      MAP_LAYER_REGISTRY.flatMap((entry) => {
        const pairs: Array<[string, string]> = [[entry.id, entry.id]];
        for (const alias of entry.aliases ?? []) {
          pairs.push([alias, entry.id]);
        }
        return pairs;
      }),
    ),
  );

export function resolveMapLayerId(id: string): string | null {
  return MAP_LAYER_ID_ALIASES[id] ?? null;
}

export function getMapLayer(id: string): MapLayerRegistryEntry | undefined {
  const canonical = resolveMapLayerId(id);
  if (!canonical) return undefined;
  return MAP_LAYER_BY_ID.get(canonical);
}

/** Default-on ids for map rest (parent applies; opening Layers must not). */
export function defaultOnLayerIds(): string[] {
  return MAP_LAYER_REGISTRY.filter((e) => e.defaultOn).map((e) => e.id);
}

export type InlineLegendView = {
  layerId: string;
  title: string;
  classes: readonly MapLayerLegendClass[];
  sourceCaption: string;
  legendUnit?: string;
  chip?: MapLayerEvidenceTag | null;
  nonCommercial: boolean;
  /** When the active zoom is below minzoom (or paint pending with no paint). */
  zoomGated: boolean;
  zoomHint: string;
  /** Lower → Higher scale line for ramp legends. */
  rampScale?: string;
};

export const LAYER_ZOOM_HINT = "Zoom in to see this layer";

/**
 * Build an inline legend from the registry (addendum §3.5 / A5).
 * GBP-LIVE £ class labels are supplied by the caller when ready; pre-£ uses
 * registry class labels (Lower → Higher).
 */
export function buildInlineLegendFromRegistry(
  entry: MapLayerRegistryEntry,
  opts: {
    mapZoom?: number;
    /** Optional override class labels (e.g. £ ranges when GBP-LIVE is on). */
    classLabels?: readonly string[];
  } = {},
): InlineLegendView {
  const { mapZoom, classLabels } = opts;
  const zoomGated =
    typeof mapZoom === "number" &&
    (mapZoom < entry.minzoom || mapZoom > entry.maxzoom);

  const classes =
    classLabels && classLabels.length === entry.classes.length
      ? entry.classes.map((row, i) => ({
          ...row,
          label: classLabels[i] ?? row.label,
        }))
      : entry.classes;

  const hasRampEnds =
    classes.some((c) => c.label === "Lower") &&
    classes.some((c) => c.label === "Higher");

  return {
    layerId: entry.id,
    title: entry.label,
    classes,
    sourceCaption: entry.sourceCaption,
    legendUnit: entry.legendUnit,
    chip: entry.chip ?? null,
    nonCommercial: Boolean(entry.nonCommercial),
    zoomGated,
    zoomHint: entry.zoomHint ?? LAYER_ZOOM_HINT,
    rampScale: hasRampEnds ? "Lower → Higher" : undefined,
  };
}

/** A1 helper — every registry entry has minzoom, maxzoom, and group. */
export function assertRegistryZoomAndGroup(
  entries: readonly MapLayerRegistryEntry[] = MAP_LAYER_REGISTRY,
): void {
  for (const entry of entries) {
    if (typeof entry.minzoom !== "number" || Number.isNaN(entry.minzoom)) {
      throw new Error(`layer ${entry.id}: minzoom must be numeric`);
    }
    if (typeof entry.maxzoom !== "number" || Number.isNaN(entry.maxzoom)) {
      throw new Error(`layer ${entry.id}: maxzoom must be numeric`);
    }
    if (!entry.group || typeof entry.group !== "string") {
      throw new Error(`layer ${entry.id}: group must be non-empty`);
    }
  }
}

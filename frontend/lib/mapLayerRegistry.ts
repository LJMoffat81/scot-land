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

/** Site-count bands. Site-type fills are not a public legend. */
const VDL_LEGEND_SWATCHES: ReadonlyArray<{ label: string; color: string }> = [
  { label: "<3", color: "#f4d35e" },
  { label: "3 or more", color: "#c45c26" },
];

/** Live Layers panel groups (accordion). */
export type MapLayerGroupKey =
  | "land"
  | "tenure"
  | "resources"
  | "nature"
  | "places";

export type MapLayerEvidenceTag = "market" | "proxy" | "shadow";

export type MapLayerLegendClass = {
  /** Visitor label (e.g. Lower, Higher, No figure here). */
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
  /** Sentence shown with the class key. */
  legendNote?: string;
  /**
   * When the map is zoomed further in than this, the layer no longer paints
   * and the row shows zoomOutHint. AGR council fill stops above zoom 7.
   */
  zoomOutAbove?: number;
  /** Exact hint when zoom is greater than zoomOutAbove. */
  zoomOutHint?: string;
  /** MapLibre layer ids this switch paints. Empty switches stay off the panel. */
  paintLayerIds?: readonly string[];
  /**
   * No geometry yet. Kept in the registry for labels, omitted from the
   * Layers panel, and listed on the roadmap.
   */
  coming?: boolean;
};

export const MAP_LAYER_GROUP_ORDER: MapLayerGroupKey[] = [
  "land",
  "tenure",
  "resources",
  "nature",
  "places",
];

export const PLACES_AND_BOUNDARIES_LABEL = "Places and boundaries";

export const TENURE_LABEL = "Who holds the land";

/** One-line Georgist note under each Layers group (W-LC-1). */
export const MAP_LAYER_GROUP_NOTES: Readonly<Record<MapLayerGroupKey, string>> =
  {
    land: "Land is worth what its location gives access to: homes, jobs, services and permission to build.",
    tenure: "Who holds land decides who collects its rent.",
    resources:
      "Oil, gas, seabed, wind and water are commons. Their rent belongs to everyone, not only the licence holder.",
    nature: "Estimates only. Never taxed.",
    places: "The official lines everything else is measured within.",
  };

const VALID_GROUPS = new Set<string>(MAP_LAYER_GROUP_ORDER);

export function mapLayerGroupNote(
  group: unknown,
  notes: unknown = MAP_LAYER_GROUP_NOTES,
): string {
  if (typeof group !== "string" || !group.trim()) {
    throw new Error("LAYERS-CARD: group must be a non-empty string");
  }
  if (!VALID_GROUPS.has(group)) {
    throw new Error(`LAYERS-CARD: unknown group '${group}'`);
  }
  if (notes === null || typeof notes !== "object" || Array.isArray(notes)) {
    throw new Error("LAYERS-CARD: notes must be an object");
  }
  const note = (notes as Record<string, unknown>)[group];
  if (typeof note !== "string" || !note.trim()) {
    throw new Error(`LAYERS-CARD: ${group}: note must be a non-empty string`);
  }
  return note.trim();
}

export function mapLayerGroupLabel(group: MapLayerGroupKey): string {
  switch (group) {
    case "land":
      return RENT_GROUP_NAME.land;
    case "tenure":
      return TENURE_LABEL;
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

const OUTLINE_CLASSES: MapLayerLegendClass[] = [
  { label: "Boundary lines", color: "#334155" },
];

/** LAYERS-ADD-1 design: deprivation purple sequential (more → less deprived). */
const DEPRIVATION_CLASSES: MapLayerLegendClass[] = [
  { label: "More deprived", color: "#3f007d" },
  { label: "·", color: "#6a51a3" },
  { label: "·", color: "#9e9ac8" },
  { label: "·", color: "#cbc9e2" },
  { label: "Less deprived", color: "#f2f0f7" },
  { label: "No figure here", color: "#bbbbbb" },
];

/** SEPA-FLOOD-1: share of the Data Zone in the medium present-day extent. */
export const FLOOD_EXTENT_LEGEND =
  "Share of this area in SEPA's medium-likelihood flood extent (today's climate)";

export const FLOOD_EXTENT_CREDIT =
  "©SEPA 2025; this SEPA product is licensed under the Open Government Licence version 3.0.";

/** MAP-VISION-1b W-1b-1 — self-explanatory dz2022 population-density key. */
export const DZ2022_DENSITY_CLASSES: readonly MapLayerLegendClass[] = [
  { label: "Up to 10 people per km²", color: "#eff3ff" },
  { label: "10–100 people per km²", color: "#bdd7e7" },
  { label: "100–500 people per km²", color: "#6baed6" },
  { label: "500–1,500 people per km²", color: "#3182bd" },
  { label: "1,500–3,000+ people per km²", color: "#08519c" },
  { label: "No value", color: "#d9d9d9" },
];

const FLOOD_RISK_CLASSES: MapLayerLegendClass[] = [
  { label: "0%", color: "#f7fbff" },
  { label: "1–10%", color: "#c6dbef" },
  { label: "11–25%", color: "#6baed6" },
  { label: "26–50%", color: "#2171b5" },
  { label: "Over 50%", color: "#08306b" },
];

const LISTED_CLASSES: MapLayerLegendClass[] = [
  { label: "Category A", color: "#7f2704" },
  { label: "Category B", color: "#d94801" },
  { label: "Category C", color: "#fd8d3c" },
];

const STOP_CLASSES: MapLayerLegendClass[] = [
  { label: "Bus", color: "#3a4a5c" },
  { label: "Train", color: "#c0392b" },
  { label: "Ferry", color: "#1f78b4" },
  { label: "Tram or subway", color: "#e67e22" },
];

/**
 * Live Layers switches only — no Coming soon / Coming later rows.
 * Ids match ScotlandMap paint toggles where they already exist.
 * LAYERS-ADD-1: HLA/LDP gated off (roadmap); flood = NFRA grid (default off).
 */
export const MAP_LAYER_REGISTRY: readonly MapLayerRegistryEntry[] = [
  {
    id: "1",
    aliases: ["agr"],
    group: "land",
    label: "Annual Ground Rent",
    minzoom: 5,
    maxzoom: 20,
    sourceCaption: "Scot-LAND model · 2023",
    legendUnit: "£ per m² of land, per year",
    classes: AGR_CLASSES,
    chip: "proxy",
    defaultOn: false,
    zoomOutAbove: 7,
    zoomOutHint: "Zoom out to see this layer",
    paintLayerIds: ["council-fill"],
  },
  {
    id: "access_services",
    group: "land",
    label: "Why it's valuable: access to services (2020 data)",
    minzoom: 0,
    maxzoom: 20,
    sourceCaption: "Scottish Government · 2020",
    classes: cividisLegendClasses(),
    chip: "proxy",
    defaultOn: false,
    paintLayerIds: ["access_services-add-fill"],
  },
  {
    id: "flood",
    group: "land",
    label: "Flood risk (SEPA)",
    minzoom: 0,
    maxzoom: 20,
    sourceCaption: FLOOD_EXTENT_CREDIT,
    classes: FLOOD_RISK_CLASSES,
    defaultOn: false,
    legendNote: FLOOD_EXTENT_LEGEND,
    paintLayerIds: ["sepa_nfra_grid-add-fill"],
    // Hidden while sepa_flood_dz is empty (LAYERS-FIX-1). Shown once loaded.
    coming: true,
  },
  {
    id: "vdl",
    group: "land",
    label: "Vacant and derelict land",
    minzoom: 10,
    maxzoom: 20,
    sourceCaption: "Improvement Service · vacant and derelict land",
    classes: VDL_CLASSES,
    chip: "proxy",
    defaultOn: false,
    coming: true,
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
    paintLayerIds: ["grid3-lines-layer"],
  },
  {
    id: "contaminated_land",
    group: "land",
    label: "Contaminated land",
    minzoom: 0,
    maxzoom: 20,
    sourceCaption: "Improvement Service · contaminated land",
    classes: [{ label: "Land on a council's contaminated land register", color: "#4d4d4d" }],
    defaultOn: false,
  },
  {
    id: "3",
    group: "resources",
    label: "Onshore wind and hydro",
    minzoom: 6,
    maxzoom: 20,
    sourceCaption: "DESNZ REPD · open data",
    classes: [{ label: "Wind and hydro sites", color: "#0d9488" }],
    chip: "proxy",
    defaultOn: false,
    paintLayerIds: ["repd-onshore-wind-circle", "repd-circle"],
  },
  {
    id: "4",
    group: "resources",
    label: "Seabed and foreshore",
    minzoom: 5,
    maxzoom: 20,
    sourceCaption: "Crown Estate Scotland · open data",
    classes: [{ label: "Seabed and foreshore leases", color: "#0369a1" }],
    chip: "market",
    defaultOn: false,
    paintLayerIds: ["crown-leases-fill"],
  },
  {
    id: "9",
    group: "resources",
    label: "Oil and gas",
    minzoom: 5,
    maxzoom: 20,
    sourceCaption: "North Sea Transition Authority · open data",
    classes: [{ label: "Oil and gas fields", color: "#57534e" }],
    nonCommercial: true,
    defaultOn: false,
    paintLayerIds: ["oil-fields-fill"],
  },
  {
    id: "8",
    group: "nature",
    label: "Peat and soil carbon",
    minzoom: 6,
    maxzoom: 20,
    sourceCaption: "NatureScot / soils research · open data",
    classes: [{ label: "Peat and soil carbon", color: "#78350f" }],
    nonCommercial: true,
    chip: "shadow",
    defaultOn: false,
    coming: true,
  },
  {
    id: "designations",
    group: "nature",
    label: "Protected nature sites",
    minzoom: 6,
    maxzoom: 20,
    sourceCaption: "NatureScot · open data",
    classes: [{ label: "Protected sites", color: "#15803d" }],
    defaultOn: false,
    paintLayerIds: ["designations-fill"],
  },
  {
    id: "crofting",
    group: "tenure",
    label: "Crofting / common grazings",
    minzoom: 6,
    maxzoom: 20,
    sourceCaption: "Crofting Commission · open lists",
    classes: [{ label: "Crofting areas", color: "#a16207" }],
    defaultOn: false,
  },
  {
    id: "councils",
    group: "places",
    label: "Council areas",
    minzoom: 5,
    maxzoom: 20,
    sourceCaption: "OS Boundary-Line · council boundaries",
    classes: OUTLINE_CLASSES,
    defaultOn: false,
    paintLayerIds: ["council-line"],
  },
  {
    id: "data_zones",
    aliases: ["dz2022"],
    group: "places",
    label: "Local areas (data zones)",
    minzoom: 0,
    maxzoom: 20,
    sourceCaption: `Scottish Government · ${DZ2022_EXTRACTION_YEAR}`,
    classes: DZ2022_DENSITY_CLASSES,
    defaultOn: true,
    paintLayerIds: ["data-zones-line"],
  },
  {
    id: "deprivation",
    group: "places",
    label: "Local deprivation by topic, 2020",
    minzoom: 0,
    maxzoom: 20,
    sourceCaption: "Scottish Government · 2020",
    classes: DEPRIVATION_CLASSES,
    defaultOn: false,
    coming: true,
  },
  {
    id: "conservation",
    group: "places",
    label: "Conservation areas",
    minzoom: 0,
    maxzoom: 20,
    sourceCaption: "Historic Environment Scotland · open data",
    classes: [{ label: "Protected for their character", color: "#8a3b8f" }],
    defaultOn: false,
    coming: true,
  },
  {
    id: "listed",
    group: "places",
    label: "Listed buildings",
    minzoom: 0,
    maxzoom: 20,
    sourceCaption: "Historic Environment Scotland · open data",
    classes: LISTED_CLASSES,
    defaultOn: false,
    coming: true,
  },
  {
    id: "stops",
    group: "places",
    label: "Bus and train stops",
    minzoom: 0,
    maxzoom: 20,
    sourceCaption: "Department for Transport · open data",
    classes: STOP_CLASSES,
    defaultOn: false,
    coming: true,
  },
  {
    id: "green_belt",
    group: "places",
    label: "Green belt",
    minzoom: 0,
    maxzoom: 20,
    sourceCaption: "Improvement Service · green belt",
    classes: [{ label: "Land kept open around towns", color: "#2e7d32" }],
    defaultOn: false,
  },
  {
    id: "school_catchments",
    group: "places",
    label: "School catchments",
    minzoom: 0,
    maxzoom: 20,
    sourceCaption: "Improvement Service · council data, years vary",
    classes: [{ label: "Area a school serves", color: "#5b6b7a" }],
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
  /** True when zoom is past zoomOutAbove (AGR overview only). */
  zoomOut: boolean;
  zoomOutHint?: string;
  /** Lower → Higher scale line for ramp legends. */
  rampScale?: string;
};

export const LAYER_ZOOM_HINT = "Zoom in to see this layer";

/** Drawer layer id → tileset keys whose manifest legends feed the inline key. */
export const REGISTRY_TILESETS_BY_DRAWER_ID: Readonly<
  Record<string, readonly string[]>
> = {
  councils: ["councils"],
  data_zones: ["dz2022"],
  "9": ["oil-fields", "platforms", "pipelines"],
};

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

const LEGEND_COLOR_RE = /^#[0-9a-fA-F]{6}$/;

/**
 * Collect legend classes from a tile manifest for a drawer layer id.
 * Returns null when tileLegends is absent or no classes are found.
 */
export function manifestLegendsForDrawerLayer(
  drawerId: unknown,
  tileLegends?: unknown,
): MapLayerLegendClass[] | null {
  if (typeof drawerId !== "string" || drawerId.trim() === "") {
    throw new Error("REGISTRY-LEGEND: drawerId must be a non-empty string");
  }
  if (tileLegends === undefined || tileLegends === null) {
    return null;
  }
  if (!isPlainObject(tileLegends)) {
    throw new Error(
      `REGISTRY-LEGEND: ${drawerId}: tileLegends must be an object`,
    );
  }
  const keys = REGISTRY_TILESETS_BY_DRAWER_ID[drawerId];
  if (!keys) return null;

  const out: MapLayerLegendClass[] = [];
  for (const key of keys) {
    const items = tileLegends[key];
    if (items === undefined || items === null) continue;
    if (!Array.isArray(items)) {
      throw new Error(
        `REGISTRY-LEGEND: ${drawerId}: tileset '${key}' legend must be an array`,
      );
    }
    for (const item of items) {
      if (!isPlainObject(item)) {
        throw new Error(
          `REGISTRY-LEGEND: ${drawerId}: tileset '${key}' legend item must be an object`,
        );
      }
      const label = item.label;
      if (typeof label !== "string" || label.trim() === "") {
        throw new Error(
          `REGISTRY-LEGEND: ${drawerId}: tileset '${key}' legend item label must be a non-empty string`,
        );
      }
      const color = item.color;
      if (typeof color !== "string" || !LEGEND_COLOR_RE.test(color)) {
        throw new Error(
          `REGISTRY-LEGEND: ${drawerId}: tileset '${key}' legend item color must be #RRGGBB`,
        );
      }
      out.push({ label, color });
    }
  }
  return out.length > 0 ? out : null;
}

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
    /** Manifest legend classes when the tile manifest supplies them. */
    manifestClasses?: readonly MapLayerLegendClass[] | null;
  } = {},
): InlineLegendView {
  const { mapZoom, classLabels, manifestClasses } = opts;
  if (
    manifestClasses !== undefined &&
    manifestClasses !== null &&
    !Array.isArray(manifestClasses)
  ) {
    throw new Error(
      `REGISTRY-LEGEND: ${entry.id}: manifestClasses must be an array`,
    );
  }
  const zoomGated =
    typeof mapZoom === "number" &&
    (mapZoom < entry.minzoom || mapZoom > entry.maxzoom);

  const baseClasses =
    manifestClasses && manifestClasses.length > 0
      ? manifestClasses
      : entry.classes;

  const classes =
    classLabels && classLabels.length === baseClasses.length
      ? baseClasses.map((row, i) => ({
          ...row,
          label: classLabels[i] ?? row.label,
        }))
      : [...baseClasses];

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
    zoomOut:
      typeof mapZoom === "number" &&
      typeof entry.zoomOutAbove === "number" &&
      mapZoom > entry.zoomOutAbove,
    zoomOutHint: entry.zoomOutHint,
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
    if (!VALID_GROUPS.has(entry.group)) {
      throw new Error(
        `LAYERS-CARD: layer ${entry.id}: unknown group '${entry.group}'`,
      );
    }
  }
}

const ESTIMATE_CHIPS = new Set<MapLayerEvidenceTag>(["proxy", "shadow"]);

/**
 * SRC-C C2 — every Scot-LAND model caption must carry a proxy or shadow chip.
 * Returns a list of error strings (empty when the registry is clean).
 */
export function checkEstimateChips(
  entries: ReadonlyArray<{
    id: string;
    sourceCaption: string;
    chip?: MapLayerEvidenceTag | null;
  }> = MAP_LAYER_REGISTRY,
): string[] {
  const errors: string[] = [];
  for (const entry of entries) {
    if (!entry.sourceCaption.startsWith("Scot-LAND model")) continue;
    const chip = entry.chip;
    if (chip == null || !ESTIMATE_CHIPS.has(chip)) {
      errors.push(
        `EST: ${entry.id}: Scot-LAND model layer must carry a proxy or shadow chip`,
      );
    }
  }
  return errors;
}

const LAYERS_ADD_EVERY_ZOOM_IDS = new Set([
  "access_services",
  "flood",
  "contaminated_land",
  "data_zones",
  "deprivation",
  "conservation",
  "listed",
  "stops",
  "green_belt",
  "school_catchments",
]);

const BARE_NUMERIC_LEGEND_RE = /^\d+([.,]\d+)?$/;

/**
 * MAP-VISION-1b MV-1b-DZ-KEY — reject legend labels that are bare numbers.
 */
export function assertNoBareNumericLegendLabels(...args: unknown[]): void {
  const entries = args.length === 0 ? MAP_LAYER_REGISTRY : args[0];
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new Error("REGISTRY-LEGEND: entries must be a non-empty array");
  }
  for (const entry of entries) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new Error("REGISTRY-LEGEND: entry must be an object");
    }
    const rec = entry as Record<string, unknown>;
    const id = rec.id;
    if (typeof id !== "string" || id.trim() === "") {
      throw new Error("REGISTRY-LEGEND: entry id must be a non-empty string");
    }
    const classes = rec.classes;
    if (!Array.isArray(classes)) {
      throw new Error(`REGISTRY-LEGEND: '${id}': classes must be an array`);
    }
    for (const item of classes) {
      if (typeof item !== "object" || item === null || Array.isArray(item)) {
        throw new Error(`REGISTRY-LEGEND: '${id}': legend item must be an object`);
      }
      const label = (item as Record<string, unknown>).label;
      if (typeof label !== "string" || label.trim() === "") {
        throw new Error(
          `REGISTRY-LEGEND: '${id}': legend label must be a non-empty string`,
        );
      }
      if (BARE_NUMERIC_LEGEND_RE.test(label.trim())) {
        throw new Error(
          `REGISTRY-LEGEND: '${id}': bare numeric legend label '${label.trim()}'`,
        );
      }
    }
  }
}

export function assertMapRegistryEveryZoom(...args: unknown[]): void {
  const entries = args.length === 0 ? MAP_LAYER_REGISTRY : args[0];
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new Error("EVERY-ZOOM: registry entries must be a non-empty array");
  }
  for (const entry of entries) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new Error("EVERY-ZOOM: registry entry must be an object");
    }
    const rec = entry as Record<string, unknown>;
    const id = rec.id;
    if (typeof id !== "string" || id.trim() === "") {
      throw new Error("EVERY-ZOOM: registry entry id must be a non-empty string");
    }
    const minzoom = rec.minzoom;
    if (
      typeof minzoom !== "number" ||
      Number.isNaN(minzoom) ||
      !Number.isInteger(minzoom) ||
      minzoom < 0
    ) {
      throw new Error(
        `EVERY-ZOOM: registry '${id}': minzoom must be a non-negative integer`,
      );
    }
    if (LAYERS_ADD_EVERY_ZOOM_IDS.has(id) && minzoom !== 0) {
      throw new Error(
        `EVERY-ZOOM: registry '${id}': minzoom must be 0, got ${minzoom}`,
      );
    }
  }
}

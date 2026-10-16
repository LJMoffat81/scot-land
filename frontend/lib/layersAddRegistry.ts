/**
 * LAYERS-ADD-1 visitor registry (design addendum v6 + licence 1a).
 * Every new layer defaults OFF. Improvement Service rows are omitted when the
 * local extract is absent (skip-when-absent).
 */

export type LayersAddFamily = "fill" | "context";

export type LayersAddRegistryRow = {
  id: string;
  layerId: string;
  group: "land" | "places";
  label: string;
  subline?: string;
  family: LayersAddFamily;
  minzoom: number;
  maxzoom: number;
  defaultOn: false;
  caption: string;
  credit: string;
  /** Improvement Service / Spatial Hub — skip when extract absent. */
  isSpatialHub?: boolean;
  /** Flagged / prohibited — never a Layers row. */
  gated?: boolean;
};

const OGL_DEFAULT =
  "Contains public sector information licensed under the Open Government Licence v3.0.";

export const LAYERS_ADD_CREDITS = {
  "C-SG":
    "Copyright Scottish Government, contains Ordnance Survey data © Crown copyright and database right 2026.",
  "C-OGL": OGL_DEFAULT,
  "C-HES":
    "Contains Historic Environment Scotland and OS data © Historic Environment Scotland and Crown Copyright and database right 2026, licensed under the Open Government Licence v3.0.",
  "C-SEPA":
    "© SEPA 2025. Licensed under the Open Government Licence 3.0.",
  "C-GB": `Green belt: Improvement Service Spatial Hub. ${OGL_DEFAULT}`,
  "C-SC": `School catchments: Improvement Service Spatial Hub. ${OGL_DEFAULT}`,
  "C-VDL": `Vacant and derelict land: Scottish Vacant and Derelict Land Survey via Improvement Service Spatial Hub. ${OGL_DEFAULT}`,
  "C-CL": `Contaminated land (confirmed): Improvement Service Spatial Hub. ${OGL_DEFAULT}`,
} as const;

/** SIMD metadata UUID (GIS addendum — replaces broken frozen-spec id). */
export const SIMD2020_SOURCE_UUID = "02866b0b-66e5-46ab-9b1c-d433dc3c2fae";

export const LAYERS_ADD_REGISTRY: LayersAddRegistryRow[] = [
  {
    id: "deprivation",
    layerId: "simd2020_domains",
    group: "places",
    label: "Local deprivation by topic, 2020",
    subline: "One topic at a time · context, not land value",
    family: "fill",
    minzoom: 8,
    maxzoom: 20,
    defaultOn: false,
    caption: "Scottish Government · 2020",
    credit: LAYERS_ADD_CREDITS["C-SG"],
  },
  {
    id: "dz2022",
    layerId: "dz2022_boundaries",
    group: "places",
    label: "Neighbourhood lines",
    family: "context",
    minzoom: 10,
    maxzoom: 20,
    defaultOn: false,
    caption: "Scottish Government · 2022",
    credit: LAYERS_ADD_CREDITS["C-SG"],
  },
  {
    id: "stops",
    layerId: "naptan_stops",
    group: "places",
    label: "Bus and train stops",
    family: "context",
    minzoom: 14,
    maxzoom: 20,
    defaultOn: false,
    caption: "Department for Transport · {YEAR}",
    credit: LAYERS_ADD_CREDITS["C-OGL"],
  },
  {
    id: "conservation",
    layerId: "hes_conservation_areas",
    // Tile property `name` is the published conservation-area designation.
    group: "places",
    label: "Conservation areas",
    family: "context",
    minzoom: 8,
    maxzoom: 20,
    defaultOn: false,
    caption: "Historic Environment Scotland · {YEAR}",
    credit: LAYERS_ADD_CREDITS["C-HES"],
  },
  {
    id: "listed",
    layerId: "hes_listed_buildings",
    group: "places",
    label: "Listed buildings",
    family: "context",
    minzoom: 14,
    maxzoom: 20,
    defaultOn: false,
    caption: "Historic Environment Scotland · {YEAR}",
    credit: LAYERS_ADD_CREDITS["C-HES"],
  },
  {
    id: "flood",
    layerId: "sepa_nfra_grid",
    group: "land",
    label: "Flood risk (SEPA)",
    family: "fill",
    minzoom: 8,
    maxzoom: 20,
    defaultOn: false,
    caption: "SEPA · {YEAR}",
    credit: LAYERS_ADD_CREDITS["C-SEPA"],
  },
  {
    id: "green_belt",
    layerId: "green_belt",
    group: "places",
    label: "Green belt",
    family: "context",
    minzoom: 8,
    maxzoom: 20,
    defaultOn: false,
    caption: "Improvement Service · {YEAR}",
    credit: LAYERS_ADD_CREDITS["C-GB"],
    isSpatialHub: true,
  },
  {
    id: "school_catchments",
    layerId: "school_catchments",
    // school_name is the published name of the school (a public institution).
    // LICENCE-ADDENDUM-1a: allowed on tiles; not a personal-data field.
    group: "places",
    label: "School catchments",
    family: "context",
    minzoom: 10,
    maxzoom: 20,
    defaultOn: false,
    caption: "Improvement Service · council data, years vary",
    credit: LAYERS_ADD_CREDITS["C-SC"],
    isSpatialHub: true,
  },
  {
    id: "vdl",
    layerId: "vdl",
    group: "land",
    label: "Vacant and derelict land",
    family: "context",
    minzoom: 10,
    maxzoom: 20,
    defaultOn: false,
    caption: "Improvement Service · {YEAR}",
    credit: LAYERS_ADD_CREDITS["C-VDL"],
    isSpatialHub: true,
  },
  {
    id: "contaminated_land",
    layerId: "contaminated_land",
    group: "land",
    label: "Contaminated land",
    family: "context",
    minzoom: 12,
    maxzoom: 20,
    defaultOn: false,
    caption: "Improvement Service · {YEAR}",
    credit: LAYERS_ADD_CREDITS["C-CL"],
    isSpatialHub: true,
  },
];

/** Roadmap-only (LICENCE-ADDENDUM-1a). Never in Layers / tiles / credits. */
export const LAYERS_ADD_WAITING = [
  {
    id: "ldp",
    title: "Planned development land",
    blurb: "Land councils have set aside for building",
    status: "Waiting for permission to use the data",
    statusShort: "Waiting for permission",
  },
  {
    id: "hls",
    title: "Land for new homes",
    blurb: "Sites a council expects to be built for homes",
    status: "Waiting for permission to use the data",
    statusShort: "Waiting for permission",
  },
] as const;

/** Listed-building tile/API allowlist: category + HES link only. */
export const LISTED_BUILDING_PROPERTY_ALLOWLIST = [
  "category",
  "hes_link",
] as const;

const BANNED_ROW_WORDS =
  /\b(SIMD|DZ|IZ|NaPTAN|SEPA|HES|SSSI|constraint|mask)\b/i;

export function layersAddRowNameOk(label: string): boolean {
  return !BANNED_ROW_WORDS.test(label);
}

export function visitorLayersAddRows(opts?: {
  spatialHubPresent?: Record<string, boolean>;
}): LayersAddRegistryRow[] {
  const present = opts?.spatialHubPresent ?? {};
  return LAYERS_ADD_REGISTRY.filter((row) => {
    if (row.gated) return false;
    // Missing or false means the extract is absent — hide the row.
    if (row.isSpatialHub && present[row.layerId] !== true) return false;
    return true;
  });
}

/** Map a tile-manifest payload onto Improvement Service presence flags. */
export function spatialHubPresenceFromManifest(
  sources: ReadonlyArray<{ layer_id?: string; display_id?: string | null }>,
): Record<string, boolean> {
  const present: Record<string, boolean> = {};
  for (const row of LAYERS_ADD_REGISTRY) {
    if (row.isSpatialHub) present[row.layerId] = false;
  }
  for (const src of sources) {
    for (const id of [src.layer_id, src.display_id]) {
      if (!id) continue;
      const row = LAYERS_ADD_REGISTRY.find(
        (entry) => entry.layerId === id || entry.id === id,
      );
      if (row?.isSpatialHub) present[row.layerId] = true;
    }
  }
  return present;
}

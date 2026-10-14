/**
 * Map layers drawer groups (Land / Resources / Nature / Limits / Boundaries).
 * Each row reuses an existing paint toggle (ledger id or catalog layer id).
 */

export type MapLayerGroupKey =
  | "land"
  | "resources"
  | "nature"
  | "limits"
  | "boundaries";

export type MapLayerEvidenceTag = "market" | "proxy" | "shadow";

export type MapDrawerLayer = {
  /** Stable toggle id (ledger row/constraint id or catalog id). */
  id: string;
  group: MapLayerGroupKey;
  label: string;
  description: string;
  /** Evidence tag chip; omit for constraints / boundary frames. */
  tag?: MapLayerEvidenceTag | null;
  /** No national paint yet — toggle stays off / disabled. */
  comingSoon?: boolean;
  licence: string;
  licenceUrl?: string;
};

export const MAP_LAYER_GROUP_ORDER: MapLayerGroupKey[] = [
  "land",
  "resources",
  "nature",
  "limits",
  "boundaries",
];

export function mapLayerGroupLabel(group: MapLayerGroupKey): string {
  switch (group) {
    case "land":
      return "Land";
    case "resources":
      return "Resources";
    case "nature":
      return "Nature";
    case "limits":
      return "Limits on use";
    case "boundaries":
      return "Boundaries";
    default: {
      const _exhaustive: never = group;
      return _exhaustive;
    }
  }
}

const OGL_V3 =
  "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/";

/** Curated map-drawer layers — paint keys match ScotlandMap ledger/catalog toggles. */
export const MAP_DRAWER_LAYERS: MapDrawerLayer[] = [
  {
    id: "1",
    group: "land",
    label: "Surface land",
    description: "Best permitted use of the land surface.",
    tag: "proxy",
    licence: "Research estimate — figures not published yet",
  },
  {
    id: "1a",
    group: "land",
    label: "Planning uplift",
    description: "Of which under surface land — planning permission effect.",
    tag: "proxy",
    comingSoon: true,
    licence: "Research estimate — figures not published yet",
  },
  {
    id: "vdl",
    group: "land",
    label: "Vacant and derelict land",
    description: "Scottish Vacant and Derelict Land Survey sites.",
    tag: "proxy",
    licence: "OGL-3.0",
    licenceUrl: OGL_V3,
  },
  {
    id: "2",
    group: "resources",
    label: "Minerals",
    description: "Below-ground mineral rent where evidence exists.",
    tag: "proxy",
    comingSoon: true,
    licence: "Research estimate — figures not published yet",
  },
  {
    id: "3",
    group: "resources",
    label: "Onshore wind and hydro",
    description: "Resource rent from wind and hydro sites.",
    tag: "proxy",
    licence: "OGL-3.0",
    licenceUrl: OGL_V3,
  },
  {
    id: "4",
    group: "resources",
    label: "Seabed and foreshore",
    description: "Crown Estate Scotland seabed and foreshore leases.",
    tag: "market",
    licence: "OGL-3.0",
    licenceUrl: OGL_V3,
  },
  {
    id: "5",
    group: "resources",
    label: "Aquaculture",
    description: "Aquaculture seabed leases (licence rent).",
    tag: "proxy",
    licence: "OGL-3.0",
    licenceUrl: OGL_V3,
  },
  {
    id: "6",
    group: "resources",
    label: "Fisheries quota",
    description: "Quota value where lease prices exist.",
    tag: "market",
    comingSoon: true,
    licence: "Research estimate — figures not published yet",
  },
  {
    id: "9",
    group: "resources",
    label: "Oil and gas",
    description: "Offshore, outside the Scottish land total — see methodology.",
    licence: "non-commercial",
    licenceUrl: "https://www.nstauthority.co.uk/data-and-insights/",
  },
  {
    id: "7",
    group: "nature",
    label: "Water scarcity",
    description: "Value of scarce water with no market price.",
    tag: "shadow",
    comingSoon: true,
    licence: "Research estimate — figures not published yet",
  },
  {
    id: "8",
    group: "nature",
    label: "Peat and soil carbon",
    description: "Unpriced peat and soil carbon.",
    tag: "shadow",
    licence: "non-commercial",
  },
  {
    id: "10",
    group: "nature",
    label: "Ecosystem services",
    description: "Broader nature services with no market price.",
    tag: "shadow",
    comingSoon: true,
    licence: "Research estimate — figures not published yet",
  },
  {
    id: "designations",
    group: "limits",
    label: "Designations (SSSI and related)",
    description: "Constraint: changes best use, adds no value.",
    licence: "OGL-3.0",
    licenceUrl: OGL_V3,
  },
  {
    id: "flood",
    group: "limits",
    label: "Flood",
    description: "Constraint: changes best use, adds no value.",
    licence: "OGL-3.0",
    licenceUrl: OGL_V3,
  },
  {
    id: "crofting",
    group: "limits",
    label: "Crofting / common grazings",
    description: "Constraint: changes best use, adds no value.",
    licence: "OGL-3.0",
    licenceUrl: OGL_V3,
  },
  {
    id: "lca",
    group: "limits",
    label: "Land capability for agriculture",
    description: "Constraint: changes best use, adds no value.",
    licence: "James Hutton Institute Open Data Licence",
    licenceUrl:
      "https://www.hutton.ac.uk/sites/default/files/files/soils/downloads/Hutton_LCA250K_OpenData.zip",
  },
  {
    id: "boundaries",
    group: "boundaries",
    label: "Land parcels",
    description: "Registers of Scotland INSPIRE index polygons.",
    licence: "Licensed under the Open Government Licence v3.0",
    licenceUrl: OGL_V3,
  },
  {
    id: "data_zones",
    group: "boundaries",
    label: "Data zones",
    description: "Data Zone boundaries 2022.",
    licence: "Open Government Licence v3.0",
    licenceUrl: OGL_V3,
  },
];


export function mapDrawerLayersByGroup(): Array<{
  key: MapLayerGroupKey;
  label: string;
  layers: MapDrawerLayer[];
}> {
  return MAP_LAYER_GROUP_ORDER.map((key) => ({
    key,
    label: mapLayerGroupLabel(key),
    layers: MAP_DRAWER_LAYERS.filter((layer) => layer.group === key),
  }));
}

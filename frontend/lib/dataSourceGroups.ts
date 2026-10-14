/**
 * /data sources table groups — Land · Resources · Nature · Limits.
 * Maps open-catalogue layer ids (and ledger roles) into the four public buckets.
 */

export type DataSourceGroupKey = "land" | "resources" | "nature" | "limits";

export const DATA_SOURCE_GROUP_ORDER: DataSourceGroupKey[] = [
  "land",
  "resources",
  "nature",
  "limits",
];

export function dataSourceGroupLabel(group: DataSourceGroupKey): string {
  switch (group) {
    case "land":
      return "Land";
    case "resources":
      return "Resources";
    case "nature":
      return "Nature";
    case "limits":
      return "Limits";
    default: {
      const _exhaustive: never = group;
      return _exhaustive;
    }
  }
}

/** Short plain-English blurb under each group heading. */
export function dataSourceGroupSummary(group: DataSourceGroupKey): string {
  switch (group) {
    case "land":
      return "Who holds land, empty sites, planned uses, and small-area boundaries.";
    case "resources":
      return "Energy, water, seabed and other extractive sources on or around the land.";
    case "nature":
      return "Woodland, peat and other nature stocks that sit outside market rents.";
    case "limits":
      return "Rules that change how land can be used. They add no money value.";
    default: {
      const _exhaustive: never = group;
      return _exhaustive;
    }
  }
}

/** Explicit id → group for catalogue rows that carry a licence_url. */
const LAYER_ID_GROUP: Record<string, DataSourceGroupKey> = {
  boundaries: "land",
  data_zones: "land",
  settlements: "land",
  localities: "land",
  vdl: "land",
  ldp: "land",
  hla: "land",
  public_crown: "land",
  community_ownership: "land",
  common_good: "land",
  la_holdings: "land",
  council_assets: "land",
  planning: "land",
  dz_context: "land",
  house_prices: "land",
  simd: "land",
  population_density: "land",
  hydro_sites: "resources",
  sepa_car: "resources",
  repd: "resources",
  repd_onshore_wind: "resources",
  crown_estate_leases: "resources",
  scotwind_intog: "resources",
  ces_aquaculture: "resources",
  nsta_oil_gas: "resources",
  nfi: "nature",
  native_woodland: "nature",
  carbon_peatland: "nature",
  sssi: "limits",
  naturescot_designations: "limits",
  flood: "limits",
  sepa_flood: "limits",
  lca: "limits",
  crofting: "limits",
  crofting_register: "limits",
  common_grazings: "limits",
};

/** Ledger row → group fallback when id is unknown. */
const LEDGER_ROW_GROUP: Record<string, DataSourceGroupKey> = {
  "1": "land",
  "1a": "land",
  "2": "resources",
  "3": "resources",
  "4": "resources",
  "5": "resources",
  "6": "resources",
  "7": "nature",
  "8": "nature",
  "9": "resources",
  "10": "nature",
};

export type CatalogSourceRow = {
  id: string;
  ledger_role?: string | null;
  ledger_row?: string | null;
  group?: string | null;
};

export function dataSourceGroupForLayer(
  layer: CatalogSourceRow,
): DataSourceGroupKey {
  const byId = LAYER_ID_GROUP[layer.id];
  if (byId) return byId;
  if (layer.ledger_role === "constraint") return "limits";
  const row = layer.ledger_row != null ? String(layer.ledger_row) : "";
  if (row && LEDGER_ROW_GROUP[row]) return LEDGER_ROW_GROUP[row];
  if (layer.group === "natural_capital") return "resources";
  if (layer.group === "ownership") return "land";
  return "land";
}

export function groupCatalogSources<T extends CatalogSourceRow>(
  layers: T[],
): Array<{ key: DataSourceGroupKey; label: string; summary: string; layers: T[] }> {
  return DATA_SOURCE_GROUP_ORDER.map((key) => ({
    key,
    label: dataSourceGroupLabel(key),
    summary: dataSourceGroupSummary(key),
    layers: layers.filter((layer) => dataSourceGroupForLayer(layer) === key),
  })).filter((bucket) => bucket.layers.length > 0);
}

/**
 * Types and helpers for GET /layers/catalog — drives LayersPanel.
 * Catalog is the product claim list; UI toggles must cover every live layer.
 */

import catalogUiToggles from "@/lib/catalogUiToggles.json";
import { apiJson } from "@/lib/api";

export type CatalogLayerStatus = "live" | "linked" | "gap" | "partial";

export type CatalogLayer = {
  id: string;
  group: string;
  status: CatalogLayerStatus | string;
  label: string;
  description?: string;
  endpoint?: string;
  tile_endpoint?: string;
  licence?: string;
  licence_url?: string;
  source_url?: string;
  spatial_hub_url?: string;
  minzoom?: number;
  also?: string;
  gaps?: unknown[];
  /** Georgist evidence tier for natural-capital overlays (not a rent). */
  value_tier?: "market" | "proxy" | "shadow" | string;
  commons_class?: string;
  publication_status?: string;
  /** Natural capital ledger mapping (FRONTEND_IA) — not a LayersPanel toggle. */
  ledger_role?:
    | "ledger-row"
    | "ledger-frame"
    | "constraint"
    | "ownership-context"
    | "data-only"
    | "benchmark"
    | "excluded"
    | string;
  /** Ledger row id: "1"…"10", "1a", or null/omitted for constraints. */
  ledger_row?: string | null;
  /** Prefer "ledger" for new layers; omit for legacy LayersPanel paint. */
  ui_surface?: "ledger" | "layers_panel" | string;
};

export type LayerCatalog = {
  version?: number;
  brief?: string;
  principle?: string;
  layers: CatalogLayer[];
  tools?: Array<{ id: string; status: string; label: string }>;
  data_policy?: Record<string, unknown>;
};

/** Catalog ids that have a LayersPanel toggle (must cover every live layer). */
export const UI_TOGGLE_LAYER_IDS: readonly string[] =
  catalogUiToggles.uiToggleIds;

/**
 * Live catalog layers that must not paint public modelled plot AGR £ or tax
 * scenarios. Toggle stays visible; active state shows an honest withheld note.
 */
export const PUBLIC_WITHHELD_LAYER_IDS = new Set<string>([
  "agr_value",
  "cell_grid",
]);

/** Fallback source / licence when the catalog omits fields (still shown in UI). */
export const LAYER_ATTRIBUTION: Record<
  string,
  { source: string; licence: string; sourceUrl?: string }
> = {
  agr_value: {
    source: "Scot-LAND residual AGR (SLRG methodology)",
    licence: "Research estimate — not a rates bill; plot £ not public yet",
  },
  boundaries: {
    source: "Registers of Scotland INSPIRE Index Polygons",
    licence: "OGL-3.0",
    sourceUrl: "https://www.ros.gov.uk/open-data",
  },
  cell_grid: {
    source: "Scot-LAND squares 3×3 m grid (internal AGR)",
    licence: "Not published on the public map until yield calibration",
  },
  data_zones: {
    source: "Scottish Government Data Zone boundaries 2011",
    licence:
      "Open Government Licence v3.0 — outlines + open rollups; no AGR £",
    sourceUrl:
      "https://www.spatialdata.gov.scot/geonetwork/srv/eng/catalog.search#/metadata/7d564e13-a967-495a-ae2f-048ffdfa4b03",
  },
  settlements: {
    source: "National Records of Scotland — Census 2022 Settlements",
    licence: "OGL-3.0",
    sourceUrl:
      "https://maps.gov.scot/server/rest/services/NRS/Census2022/MapServer",
  },
  localities: {
    source: "National Records of Scotland — Census 2022 Localities",
    licence: "OGL-3.0",
    sourceUrl:
      "https://maps.gov.scot/server/rest/services/NRS/Census2022/MapServer",
  },
  vdl: {
    source: "Scottish Vacant and Derelict Land Survey",
    licence: "OGL-3.0",
    sourceUrl:
      "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/",
  },
  flood: {
    source: "SEPA Flood Maps v3.0",
    licence: "OGL-3.0",
    sourceUrl: "https://www2.sepa.org.uk/flooddata/",
  },
  hla: {
    source: "Spatial Hub Housing Land Supply (Housing Land Audit)",
    licence: "OGL-3.0",
    sourceUrl: "https://data.spatialhub.scot/dataset/housing_land_supply-is",
  },
  ldp_allocations: {
    source: "Spatial Hub — Local Development Plans (Scotland)",
    licence: "OGL-3.0",
    sourceUrl: "https://data.spatialhub.scot/dataset/local_development_plans-is",
  },
  public_crown: {
    source: "Scottish Public and Crown Estate Land 2024",
    licence: "unverified/not open",
    sourceUrl:
      "https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897",
  },
  hydro_sites: {
    source: "SEPA Hydropower Sites (CAR)",
    licence: "OGL-3.0",
    sourceUrl:
      "https://www.data.gov.uk/dataset/5750f8e5-d51b-4e75-a8d6-403a0d1ded81/hydropower_sites",
  },
  sepa_car: {
    source: "SEPA CAR licences (MapServer 194/195 → PostGIS)",
    licence: "OGL-3.0",
    sourceUrl: "https://www.sepa.org.uk/environment/environmental-data/",
  },
  sssi: {
    source: "NatureScot Sites of Special Scientific Interest",
    licence: "OGL-3.0",
    sourceUrl:
      "https://opendata.nature.scot/maps/sites-of-special-scientific-interest",
  },
  naturescot_designations: {
    source: "NatureScot designations (SPA, SAC, NNR)",
    licence: "OGL-3.0",
    sourceUrl: "https://opendata.nature.scot/",
  },
  dz_house_price: {
    source: "RoS residential sales (DZ) + UK HPI council averages",
    licence: "OGL v3.0",
    sourceUrl:
      "https://data.gov.scot/dataset/house_prices___residential_properties_sales_and_price",
  },
  dz_simd: {
    source: "SIMD 2020v2 (Scottish Government)",
    licence: "OGL v3.0",
    sourceUrl:
      "https://www.gov.scot/publications/scottish-index-of-multiple-deprivation-2020v2-data-zone-look-up/",
  },
  dz_pop_density: {
    source: "NRS small area population estimates ÷ zone area",
    licence: "OGL v3.0",
    sourceUrl:
      "https://www.nrscotland.gov.uk/publications/small-area-population-estimates-mid-2024-2022-data-zones/",
  },
  repd: {
    source: "DESNZ Renewable Energy Planning Database (REPD)",
    licence: "OGL-3.0",
    sourceUrl:
      "https://www.gov.uk/government/publications/renewable-energy-planning-database-quarterly-extract",
  },
  crown_estate_leases: {
    source: "Crown Estate Scotland Spatial Hub offshore leases",
    licence: "OGL-3.0",
    sourceUrl:
      "https://crown-estate-scotland-spatial-hub-coregis.hub.arcgis.com/",
  },

  community_ownership: {
    source:
      "Community Ownership in Scotland 2024 (postcodes.io / ONS Postcode Directory centroids)",
    licence:
      "Open Government Licence v3.0 — Contains OS data © Crown copyright and database right 2026; Contains Royal Mail data © Royal Mail copyright and database right 2026; Contains National Statistics data © Crown copyright and database right 2026",
    sourceUrl:
      "https://www.gov.scot/publications/community-ownership-in-scotland-2024/",
  },
  nfi: {
    source: "National Forest Inventory Woodland Scotland",
    licence: "Open Government Licence v3.0",
    sourceUrl:
      "https://www.data.gov.uk/dataset/c50cddf4-cdf0-42fb-8ac1-eae0cb6ef5ad/national-forest-inventory-scotland-2025",
  },
  native_woodland: {
    source: "Native Woodland Survey of Scotland",
    licence: "Open Government Licence v3.0",
    sourceUrl:
      "https://www.data.gov.uk/dataset/da3f8548-a130-4a0d-8ddd-45019adcf1f3/native-woodland-survey-of-scotland-nwss",
  },
  la_holdings: {
    source: "Spatial Hub — Land Ownership Scotland",
    licence: "Not openly licensed for this portal",
    sourceUrl:
      "https://data.spatialhub.scot/dataset/land_ownership-is",
  },
  planning: {
    source: "ePlanning Scotland / council registers",
    licence: "Official pages (linked)",
    sourceUrl: "https://www.eplanning.scot/ePlanningClient/",
  },
  council_assets: {
    source: "Improvement Service Spatial Hub",
    licence: "Login-gated — not mirrored",
    sourceUrl:
      "https://data.spatialhub.scot/dataset/council_asset_register-is",
  },
  common_good: {
    source: "Council Common Good registers",
    licence:
      "Linked registers; Highland licence unconfirmed; Fife OS INSPIRE EUL linked only",
    sourceUrl:
      "https://www.highland.gov.uk/community-support-development/common-good-asset-register",
  },
  crofting_register: {
    source: "Crofting Commission Register of Crofts",
    licence: "OGL-3.0",
    sourceUrl: "https://www.crofting.scotland.gov.uk/open-data/",
  },
  common_grazings: {
    source: "Crofting Commission List of Grazings",
    licence: "OGL-3.0",
    sourceUrl: "https://www.crofting.scotland.gov.uk/open-data/",
  },
  fife_land_map: {
    source: "Fife Council ArcGIS hub",
    licence: "Council hub (not a national layer)",
    sourceUrl: "https://fife.maps.arcgis.com/home/index.html",
  },
  sasine_private: {
    source: "Sasine / private ownership",
    licence: "Incomplete or paid — gaps shown, names not invented",
  },
};

export const WITHHELD_PUBLIC_MESSAGE =
  "Not on the public map yet. Modelled plot Annual Ground Rent and Scot-LAND squares stay internal until yield calibration. No public tax scenarios.";

export function layerSource(layer: CatalogLayer): string {
  const fallback = LAYER_ATTRIBUTION[layer.id];
  if (layer.source_url) return layer.source_url;
  return fallback?.sourceUrl || fallback?.source || "Source not listed in catalog";
}

export function layerLicence(layer: CatalogLayer): string {
  if (layer.licence?.trim()) return layer.licence;
  return LAYER_ATTRIBUTION[layer.id]?.licence || "Licence not listed in catalog";
}

export function layerSourceLabel(layer: CatalogLayer): string {
  const fallback = LAYER_ATTRIBUTION[layer.id];
  if (fallback?.source) return fallback.source;
  if (layer.source_url) return layer.source_url;
  return "Source not listed in catalog";
}

export async function fetchLayerCatalog(): Promise<LayerCatalog> {
  const payload = await apiJson<LayerCatalog>("/layers/catalog");
  if (!payload || !Array.isArray(payload.layers)) {
    throw new Error("Layer catalog response missing layers");
  }
  return payload;
}

export function liveCatalogLayerIds(catalog: LayerCatalog): string[] {
  return catalog.layers
    .filter((layer) => layer.status === "live")
    .map((layer) => layer.id);
}

export function groupLabel(group: string): string {
  switch (group) {
    case "value":
      return "Value";
    case "spatial":
      return "Spatial";
    case "ownership":
      return "Ownership";
    default:
      return group;
  }
}

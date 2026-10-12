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
  source_url?: string;
  spatial_hub_url?: string;
  minzoom?: number;
  also?: string;
  gaps?: unknown[];
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
    source: "Registers of Scotland INSPIRE",
    licence: "OGL / INSPIRE (Crown)",
    sourceUrl: "https://www.ros.gov.uk/open-data",
  },
  cell_grid: {
    source: "What3Words 3×3 m cell grid (internal AGR)",
    licence: "Not published on the public map until yield calibration",
  },
  vdl: {
    source: "Scottish Vacant and Derelict Land Survey",
    licence: "OGL-3.0",
    sourceUrl:
      "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/",
  },
  public_crown: {
    source: "Scottish Public and Crown Estate Land 2024",
    licence: "OGL-3.0",
    sourceUrl:
      "https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897",
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
    licence: "Linked registers; no national open map layer",
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
  "Not on the public map yet. Modelled plot Annual Ground Rent and the W3W rent grid stay internal until yield calibration. No public tax scenarios.";

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

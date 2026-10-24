/**
 * Paint for LAYERS-ADD rows that used to be switches with no map layer.
 * Flood risk (visitor id "flood") paints catalog layer sepa_nfra_grid.
 */

import type { ExpressionSpecification, GeoJSONSource, Map } from "maplibre-gl";
import { apiJson } from "./api";
import { LAYERS_ADD_CREDITS, LAYERS_ADD_REGISTRY } from "./layersAddRegistry";

export type FloodKind = "river" | "coastal" | "surface";

const FLOOD_BAND_COLORS = ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"] as const;

/** 0, 1–10, 11–25, 26–50, and over 50 per cent of the Data Zone. */
export function floodFillColor(kind: FloodKind): ExpressionSpecification {
  const field =
    kind === "coastal"
      ? "pct_area_coastal"
      : kind === "surface"
        ? "pct_area_surface"
        : "pct_area_river";
  return [
    "step",
    ["coalesce", ["to-number", ["get", field]], 0],
    FLOOD_BAND_COLORS[0],
    1,
    FLOOD_BAND_COLORS[1],
    11,
    FLOOD_BAND_COLORS[2],
    26,
    FLOOD_BAND_COLORS[3],
    51,
    FLOOD_BAND_COLORS[4],
  ] as ExpressionSpecification;
}

export type LayersAddPaintKind = "fill" | "circle";

export type LayersAddPaintSpec = {
  /** Visitor toggle id in the Layers panel. */
  displayId: string;
  /** Catalog layer id requested from the viewport route and used on the map. */
  catalogLayerId: string;
  kind: LayersAddPaintKind;
  color: string;
  minzoom: number;
  attribution: string;
};

function catalogId(displayId: string): string {
  return (
    LAYERS_ADD_REGISTRY.find((row) => row.id === displayId)?.layerId ??
    displayId
  );
}

/** The nine rows that were paint-pending. Each one has a real map layer. */
export const LAYERS_ADD_PAINT: readonly LayersAddPaintSpec[] = [
  {
    displayId: "access_services",
    catalogLayerId: "access_services",
    kind: "fill",
    color: "#3b528b",
    minzoom: 0,
    attribution: LAYERS_ADD_CREDITS["C-SG"],
  },
  {
    displayId: "flood",
    catalogLayerId: catalogId("flood"),
    kind: "fill",
    color: "#2b6cb0",
    minzoom: 0,
    attribution: LAYERS_ADD_CREDITS["C-SEPA"],
  },
  {
    displayId: "contaminated_land",
    catalogLayerId: catalogId("contaminated_land"),
    kind: "fill",
    color: "#4d4d4d",
    minzoom: 0,
    attribution: LAYERS_ADD_CREDITS["C-CL"],
  },
  {
    displayId: "deprivation",
    catalogLayerId: catalogId("deprivation"),
    kind: "fill",
    color: "#6b4c9a",
    minzoom: 0,
    attribution: LAYERS_ADD_CREDITS["C-SG"],
  },
  {
    displayId: "conservation",
    catalogLayerId: catalogId("conservation"),
    kind: "fill",
    color: "#8a3b8f",
    minzoom: 0,
    attribution: LAYERS_ADD_CREDITS["C-HES"],
  },
  {
    displayId: "listed",
    catalogLayerId: catalogId("listed"),
    kind: "circle",
    color: "#6b2d5b",
    minzoom: 0,
    attribution: LAYERS_ADD_CREDITS["C-HES"],
  },
  {
    displayId: "stops",
    catalogLayerId: catalogId("stops"),
    kind: "circle",
    color: "#1f4e79",
    minzoom: 0,
    attribution: LAYERS_ADD_CREDITS["C-OGL"],
  },
  {
    displayId: "green_belt",
    catalogLayerId: catalogId("green_belt"),
    kind: "fill",
    color: "#2e7d32",
    minzoom: 0,
    attribution: LAYERS_ADD_CREDITS["C-GB"],
  },
  {
    displayId: "school_catchments",
    catalogLayerId: catalogId("school_catchments"),
    kind: "fill",
    color: "#5b6b7a",
    minzoom: 0,
    attribution: LAYERS_ADD_CREDITS["C-SC"],
  },
];

const EMPTY_FC: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

export function layersAddSourceId(spec: LayersAddPaintSpec): string {
  return `${spec.catalogLayerId}-add`;
}

export function layersAddLayerId(spec: LayersAddPaintSpec): string {
  return `${spec.catalogLayerId}-add-${spec.kind}`;
}

export function ensureLayersAddPaint(map: Map): void {
  if (!styleIsReady(map)) return;
  for (const spec of LAYERS_ADD_PAINT) {
    const sourceId = layersAddSourceId(spec);
    if (!map.getSource(sourceId)) {
      map.addSource(sourceId, {
        type: "geojson",
        data: EMPTY_FC,
        attribution: spec.attribution,
      });
    }
    const layerId = layersAddLayerId(spec);
    if (map.getLayer(layerId)) continue;
    if (spec.kind === "fill") {
      map.addLayer({
        id: layerId,
        type: "fill",
        source: sourceId,
        minzoom: spec.minzoom,
        layout: { visibility: "none" },
        paint: {
          "fill-color":
            spec.displayId === "flood" ? floodFillColor("river") : spec.color,
          "fill-opacity": spec.displayId === "flood" ? 0.72 : 0.45,
        },
      });
      continue;
    }
    map.addLayer({
      id: layerId,
      type: "circle",
      source: sourceId,
      minzoom: spec.minzoom,
      layout: { visibility: "none" },
      paint: {
        "circle-radius": 6,
        "circle-color": spec.color,
        "circle-stroke-width": 1,
        "circle-stroke-color": "#ffffff",
      },
    });
  }
}

function setSourceData(
  map: Map,
  sourceId: string,
  data: GeoJSON.FeatureCollection,
): void {
  const src = map.getSource(sourceId) as GeoJSONSource | undefined;
  if (!src || src.type !== "geojson") return;
  src.setData(data);
}

const SPATIAL_HUB_CATALOG_IDS = new Set(
  LAYERS_ADD_REGISTRY.filter((row) => row.isSpatialHub).map((row) => row.layerId),
);

/** Show or hide each painted row and load viewport shapes when one is on. */
function styleIsReady(map: Map): boolean {
  try {
    return Boolean(map.getStyle()?.layers);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err ?? "");
    if (message.includes("Style is not done loading")) return false;
    throw err;
  }
}

export async function syncLayersAddPaint(
  map: Map,
  enabled: Record<string, boolean | undefined>,
  spatialHubPresent?: Record<string, boolean> | null,
  floodKind: FloodKind = "river",
): Promise<void> {
  if (!styleIsReady(map)) return;
  const bounds = map.getBounds();
  const jobs: Array<Promise<void>> = [];
  try {
    ensureLayersAddPaint(map);
    for (const spec of LAYERS_ADD_PAINT) {
      const layerId = layersAddLayerId(spec);
      const on = Boolean(enabled[spec.displayId]);
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, "visibility", on ? "visible" : "none");
        if (spec.displayId === "flood") {
          map.setPaintProperty(layerId, "fill-color", floodFillColor(floodKind));
        }
      }
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err ?? "");
    if (message.includes("Style is not done loading")) return;
    throw err;
  }
  for (const spec of LAYERS_ADD_PAINT) {
    const on = Boolean(enabled[spec.displayId]);
    if (!on || !bounds || map.getZoom() < spec.minzoom) continue;
    // Improvement Service outlines are requested only once the extract exists.
    if (
      SPATIAL_HUB_CATALOG_IDS.has(spec.catalogLayerId) &&
      spatialHubPresent?.[spec.catalogLayerId] !== true &&
      spatialHubPresent?.[spec.displayId] !== true
    ) {
      continue;
    }
    const path =
      spec.displayId === "flood"
        ? `/layers/open/flood-dz?bbox=${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}&kind=${floodKind}`
        : `/layers/add/viewport/${spec.catalogLayerId}` +
          `?south=${bounds.getSouth()}&west=${bounds.getWest()}` +
          `&north=${bounds.getNorth()}&east=${bounds.getEast()}`;
    const sourceId = layersAddSourceId(spec);
    jobs.push(
      apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (data?.type === "FeatureCollection") setSourceData(map, sourceId, data);
        })
        .catch(() => {
          setSourceData(map, sourceId, EMPTY_FC);
        }),
    );
  }
  await Promise.all(jobs);
}

export function assertLayersAddPaintEveryZoom(...args: unknown[]): void {
  const specs = args.length === 0 ? LAYERS_ADD_PAINT : args[0];
  if (!Array.isArray(specs) || specs.length === 0) {
    throw new Error(
      "EVERY-ZOOM: layersAddPaint specs must be a non-empty array",
    );
  }
  for (const spec of specs) {
    if (typeof spec !== "object" || spec === null || Array.isArray(spec)) {
      throw new Error("EVERY-ZOOM: layersAddPaint spec must be an object");
    }
    const rec = spec as Record<string, unknown>;
    const displayId = rec.displayId;
    if (typeof displayId !== "string" || displayId.trim() === "") {
      throw new Error(
        "EVERY-ZOOM: layersAddPaint displayId must be a non-empty string",
      );
    }
    const minzoom = rec.minzoom;
    if (
      typeof minzoom !== "number" ||
      Number.isNaN(minzoom) ||
      !Number.isInteger(minzoom)
    ) {
      throw new Error(
        `EVERY-ZOOM: layersAddPaint '${displayId}': minzoom must be an integer`,
      );
    }
    if (minzoom !== 0) {
      throw new Error(
        `EVERY-ZOOM: layersAddPaint '${displayId}': minzoom must be 0, got ${minzoom}`,
      );
    }
  }
}

/**
 * River and coastal medium-likelihood flood images from SEPA's OGL service.
 * MapLibre fills {bbox-epsg-3857} and the browser requests each image.
 * Nothing is stored.
 */

import type { Map } from "maplibre-gl";

export const SEPA_FLOOD_SERVICE =
  "https://map.sepa.org.uk/server/rest/services/Open/Flood_Maps/MapServer/export";

/** MapServer ids: river medium = 1, coastal medium = 7. */
export const SEPA_FLOOD_LIVE = [
  {
    id: "flood_river",
    mapLayer: 1,
    sourceId: "sepa-flood-river",
    layerId: "sepa-flood-river",
  },
  {
    id: "flood_coastal",
    mapLayer: 7,
    sourceId: "sepa-flood-coastal",
    layerId: "sepa-flood-coastal",
  },
] as const;

/** Export URL template. MapLibre replaces {bbox-epsg-3857}. */
export function sepaFloodTileTemplate(mapLayer: number): string {
  return (
    `${SEPA_FLOOD_SERVICE}?bbox={bbox-epsg-3857}` +
    "&bboxSR=3857&imageSR=3857&size=256,256&format=png32" +
    `&transparent=true&layers=show:${mapLayer}&f=image`
  );
}

export function syncSepaFloodLiveLayers(
  map: Map,
  enabled: Record<string, boolean | undefined>,
): void {
  for (const row of SEPA_FLOOD_LIVE) {
    if (!map.getSource(row.sourceId)) {
      map.addSource(row.sourceId, {
        type: "raster",
        tiles: [sepaFloodTileTemplate(row.mapLayer)],
        tileSize: 256,
      });
    }
    if (!map.getLayer(row.layerId)) {
      map.addLayer({
        id: row.layerId,
        type: "raster",
        source: row.sourceId,
        minzoom: 6,
        paint: {
          "raster-opacity": 0.72,
          "raster-fade-duration": 0,
        },
        layout: { visibility: "none" },
      });
    }
    map.setLayoutProperty(
      row.layerId,
      "visibility",
      enabled[row.id] ? "visible" : "none",
    );
  }
}

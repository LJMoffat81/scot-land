/**
 * MAP-CARDS GIS 14 — one attribution line from active layers.
 */

import { dzAttributionText } from "./dzAttribution";
import { inspireRosOsAttribution } from "./inspireAttribution";
import { layersAdd2Credit } from "./layersAdd2Credits";
import { getMapLayer } from "./mapLayerRegistry";

/** Always present basemap credit. */
export const OPENFREEMAP_ATTRIBUTION =
  "© OpenFreeMap © OpenStreetMap";

/** Vacant-land credit when that layer is on. Zone totals only. */
export const VDL_ZONE_TOTALS_ATTRIBUTION =
  "Totals from the Scottish Vacant and Derelict Land Survey, grouped by Data Zone. Zones with one or two sites show no area.";

/** RoS credit when any RoS-backed layer is on (parcels removed; keep for future). */
export const ROS_LAYER_IDS = new Set<string>([
  "boundaries",
  "parcels",
  "crofting",
]);

export type AttributionPiece = {
  id: string;
  text: string;
};

/**
 * Build credit pieces for the active toggle ids.
 * Basemap credit is always first; "All sources" is rendered separately in UI.
 */
export function buildMapAttributionPieces(
  enabledIds: readonly string[],
): AttributionPiece[] {
  const pieces: AttributionPiece[] = [
    { id: "basemap", text: OPENFREEMAP_ATTRIBUTION },
  ];
  const on = new Set(
    enabledIds.map((id) => getMapLayer(id)?.id ?? id).filter(Boolean),
  );

  if (on.has("data_zones")) {
    pieces.push({ id: "data_zones", text: dzAttributionText() });
  }
  if (on.has("vdl")) {
    pieces.push({ id: "vdl", text: VDL_ZONE_TOTALS_ATTRIBUTION });
  }

  let ros = false;
  for (const id of on) {
    if (ROS_LAYER_IDS.has(id)) {
      ros = true;
      break;
    }
  }
  if (ros) {
    pieces.push({ id: "ros", text: inspireRosOsAttribution() });
  }

  for (const id of on) {
    const credit = layersAdd2Credit(id);
    if (!credit) continue;
    pieces.push({ id, text: credit });
  }

  return pieces;
}

export function formatAttributionLine(
  enabledIds: readonly string[],
): string {
  return buildMapAttributionPieces(enabledIds)
    .map((p) => p.text)
    .join(" · ");
}

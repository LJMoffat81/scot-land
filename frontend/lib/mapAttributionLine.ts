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

/**
 * Short on-map source name for a non-basemap piece.
 * Long licence text may sit in the ⓘ sheet on narrow screens; the short
 * name stays visible (Wording & UX: e.g. "Flood maps: SEPA").
 */
export function shortLayerSourceName(
  piece: AttributionPiece,
): string | null {
  if (piece.id === "basemap") return null;
  switch (piece.id) {
    case "data_zones":
      return "Data zones: Scottish Government";
    case "vdl":
      return "Vacant land: SVDLS";
    case "ros":
      return "Boundaries: RoS / OS";
    case "nrs_dz_pop_hh":
      return "Population and households: NRS";
    case "epc_domestic":
      return "Domestic energy certificates: OGL";
    case "ofcom_cn_fixed":
      return "Broadband: Ofcom";
    case "sg_urban_rural":
      return "Town and country: Scottish Government";
    case "os_open_roads":
      return "Roads: OS";
    case "os_open_greenspace":
      return "Parks and green spaces: OS";
    case "os_open_rivers":
      return "Rivers: OS";
    case "fls_estate":
      return "Public forests and land: FLS";
    case "ces_assets":
      return "Crown Estate Scotland assets: CES";
    case "flood":
      return "Flood maps: SEPA";
    default: {
      const add2 = layersAdd2Credit(piece.id);
      if (!add2) return null;
      return piece.id.replace(/_/g, " ");
    }
  }
}

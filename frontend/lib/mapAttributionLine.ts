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

/** Scotland land-and-waters outline — registry attribution, one line (SEA-EXTENT-2). */
export const SCOTLAND_EXTENT_CREDIT =
  "Contains public sector information, licensed under the Open Government Licence v3.0, from UK Hydrographic Office. Contains OS data © Crown copyright and database right 2026.";

/** Vacant-land credit when that layer is on. Zone totals only. */
export const VDL_ZONE_TOTALS_ATTRIBUTION =
  "Totals from the Scottish Vacant and Derelict Land Survey, grouped by Data Zone. Zones with one or two sites show no area.";

/** NSTA oil/gas tilesets — registry attribution (oil-fields / platforms / pipelines). */
export const NSTA_ATTRIBUTION =
  "Contains information provided by the North Sea Transition Authority and/or other third parties.";

/** RoS credit when any RoS-backed layer is on (parcels removed; keep for future). */
export const ROS_LAYER_IDS = new Set<string>([
  "boundaries",
  "parcels",
  "crofting",
]);

const OIL_GAS_TILESET_KEYS = [
  "oil-fields",
  "platforms",
  "pipelines",
] as const;

export type AttributionPiece = {
  id: string;
  text: string;
};

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * Resolve a tileset credit from the manifest map, falling back when absent.
 */
export function resolveTileCredit(
  key: string,
  fallback: string,
  tileCredits?: unknown,
): string {
  if (typeof key !== "string" || key.trim() === "") {
    throw new Error("REGISTRY-CREDIT: key must be a non-empty string");
  }
  if (tileCredits === undefined || tileCredits === null) {
    return fallback;
  }
  if (!isPlainObject(tileCredits)) {
    throw new Error("REGISTRY-CREDIT: tileCredits must be an object");
  }
  const val = tileCredits[key];
  if (val === undefined || val === null) {
    return fallback;
  }
  if (typeof val !== "string" || val.trim() === "") {
    throw new Error(
      `REGISTRY-CREDIT: ${key}: credit must be a non-empty string`,
    );
  }
  return val.trim();
}

/**
 * Build credit pieces for the active toggle ids.
 * Basemap credit is always first; "All sources" is rendered separately in UI.
 */
export function buildMapAttributionPieces(
  enabledIds: readonly string[],
  tileCredits?: Readonly<Record<string, string>> | null,
): AttributionPiece[] {
  if (
    tileCredits !== undefined &&
    tileCredits !== null &&
    !isPlainObject(tileCredits)
  ) {
    throw new Error("REGISTRY-CREDIT: tileCredits must be an object");
  }

  const pieces: AttributionPiece[] = [
    { id: "basemap", text: OPENFREEMAP_ATTRIBUTION },
  ];
  const on = new Set(
    enabledIds.map((id) => getMapLayer(id)?.id ?? id).filter(Boolean),
  );

  if (on.has("scotland-extent")) {
    pieces.push({
      id: "scotland-extent",
      text: resolveTileCredit(
        "scotland-extent",
        SCOTLAND_EXTENT_CREDIT,
        tileCredits,
      ),
    });
  }
  if (on.has("data_zones")) {
    pieces.push({
      id: "data_zones",
      text: resolveTileCredit("dz2022", dzAttributionText(), tileCredits),
    });
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

  if (on.has("9")) {
    let text = NSTA_ATTRIBUTION;
    if (tileCredits) {
      for (const key of OIL_GAS_TILESET_KEYS) {
        const val = tileCredits[key];
        if (val !== undefined && val !== null) {
          text = resolveTileCredit(key, NSTA_ATTRIBUTION, tileCredits);
          break;
        }
      }
    }
    pieces.push({ id: "9", text });
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
  tileCredits?: Readonly<Record<string, string>> | null,
): string {
  return buildMapAttributionPieces(enabledIds, tileCredits)
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
    case "scotland-extent":
      return "Scotland outline: UKHO / OS";
    case "data_zones":
      return "Data zones: Scottish Government";
    case "vdl":
      return "Vacant land: SVDLS";
    case "ros":
      return "Boundaries: RoS / OS";
    case "9":
      return "Oil and gas: NSTA";
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

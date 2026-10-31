/**
 * Place-card "What's nearby" facts — live registry layers only.
 * CARD-CLARITY-31OCT-1B item 8.
 */

import { getMapLayer, MAP_LAYER_REGISTRY } from "./mapLayerRegistry";
import type { PlaceConstraintRow } from "./placeCard";

export const NEARBY_FACT_LAYER_IDS = [
  "flood",
  "designations",
  "crofting",
] as const;

export type NearbyFactLayerId = (typeof NEARBY_FACT_LAYER_IDS)[number];

export const NEARBY_FACT_TEXT: Readonly<
  Record<NearbyFactLayerId, Readonly<{ yes: string; no: string }>>
> = {
  flood: {
    yes: "Includes a SEPA flood risk area",
    no: "No SEPA flood risk area mapped here",
  },
  designations: {
    yes: "Includes a protected nature site",
    no: "No protected nature site mapped here",
  },
  crofting: {
    yes: "Includes crofting land",
    no: "No crofting land mapped here",
  },
};

export type NearbyFact = {
  id: NearbyFactLayerId;
  text: string;
};

/** True when the layer is live on the map (drawer-visible rule). */
export function isLiveRegistryLayer(
  id: string,
  opts?: { floodLoaded?: boolean },
): boolean {
  const entry = getMapLayer(id);
  if (!entry) return false;
  if (entry.paintPending) return false;
  if (entry.coming) {
    return id === "flood" && Boolean(opts?.floodLoaded);
  }
  return true;
}

/**
 * Fail closed when a nearby id is missing from the registry.
 * Call with an explicit list to probe unknown ids in tests.
 */
export function assertNearbyLayerIdsInRegistry(
  ids: readonly string[] = NEARBY_FACT_LAYER_IDS,
): void {
  for (const id of ids) {
    if (!MAP_LAYER_REGISTRY.some((entry) => entry.id === id)) {
      throw new Error(`NEARBY: layer id '${id}' is not in MAP_LAYER_REGISTRY`);
    }
  }
}

/**
 * Build visitor nearby facts from place constraints.
 * Drops unknown / non-live ids and any `applies` that is not a boolean.
 */
export function placeNearbyFacts(
  constraints: readonly PlaceConstraintRow[] | null | undefined,
  opts?: { floodLoaded?: boolean },
): NearbyFact[] {
  assertNearbyLayerIdsInRegistry();
  const byId = new Map<string, PlaceConstraintRow>();
  for (const row of constraints ?? []) {
    if (row && typeof row.id === "string") byId.set(row.id, row);
  }
  const out: NearbyFact[] = [];
  for (const id of NEARBY_FACT_LAYER_IDS) {
    if (!isLiveRegistryLayer(id, opts)) continue;
    const row = byId.get(id);
    if (!row || typeof row.applies !== "boolean") continue;
    const copy = NEARBY_FACT_TEXT[id];
    out.push({ id, text: row.applies ? copy.yes : copy.no });
  }
  return out;
}

/**
 * Map layers drawer groups — derived from the live layer registry.
 * Live switches only; deferred layers live on /roadmap (MAP-CARDS E7).
 */

import { LAYERS_ADD_REGISTRY, visitorLayersAddRows } from "./layersAddRegistry";
import {
  MAP_LAYER_GROUP_ORDER,
  MAP_LAYER_REGISTRY,
  mapLayerGroupLabel,
  type MapLayerEvidenceTag,
  type MapLayerGroupKey,
  type MapLayerRegistryEntry,
} from "./mapLayerRegistry";

export type { MapLayerEvidenceTag, MapLayerGroupKey };
export { MAP_LAYER_GROUP_ORDER, mapLayerGroupLabel };

export type MapDrawerLayer = {
  /** Stable toggle id (paint / URL). */
  id: string;
  group: MapLayerGroupKey;
  label: string;
  /** Evidence tag for inline legend chip only. */
  tag?: MapLayerEvidenceTag | null;
  /** @deprecated Deferred layers are on /roadmap, not in the live registry. */
  comingSoon?: boolean;
  /** Source · year caption (legacy field name kept for licence helpers). */
  licence: string;
  licenceUrl?: string;
  minzoom: number;
  maxzoom: number;
  sourceCaption: string;
  nonCommercial?: boolean;
  defaultOn?: boolean;
  paintPending?: boolean;
  /** Accessible description under the switch (e.g. grid3 subline). */
  subline?: string;
  /** No geometry yet — omitted from the panel (roadmap lists it). */
  coming?: boolean;
};

function toDrawerLayer(entry: MapLayerRegistryEntry): MapDrawerLayer {
  return {
    id: entry.id,
    group: entry.group,
    label: entry.label,
    tag: entry.chip ?? null,
    licence: entry.sourceCaption,
    minzoom: entry.minzoom,
    maxzoom: entry.maxzoom,
    sourceCaption: entry.sourceCaption,
    nonCommercial: entry.nonCommercial,
    defaultOn: entry.defaultOn,
    paintPending: entry.paintPending,
    subline: entry.subline,
    coming: entry.coming,
  };
}

/** Curated live drawer layers — paint keys match ScotlandMap toggles. */
export const MAP_DRAWER_LAYERS: MapDrawerLayer[] =
  MAP_LAYER_REGISTRY.map(toDrawerLayer);

/**
 * Visitor drawer groups.
 * Improvement Service rows stay off the list until the extract is present.
 * A row still marked paintPending stays hidden (no dead switch).
 */
export function mapDrawerLayersByGroup(opts?: {
  spatialHubPresent?: Record<string, boolean> | null;
  /** SEPA flood Data Zone table has rows — the flood switch may show. */
  floodLoaded?: boolean;
}): Array<{
  key: MapLayerGroupKey;
  label: string;
  layers: MapDrawerLayer[];
}> {
  const present = opts?.spatialHubPresent ?? {};
  const visibleHub = new Set(
    visitorLayersAddRows({ spatialHubPresent: present })
      .filter((row) => row.isSpatialHub)
      .map((row) => row.id),
  );
  return MAP_LAYER_GROUP_ORDER.map((key) => ({
    key,
    label: mapLayerGroupLabel(key),
    layers: MAP_DRAWER_LAYERS.filter((layer) => {
      if (layer.group !== key) return false;
      if (layer.paintPending) return false;
      if (layer.coming && !(layer.id === "flood" && opts?.floodLoaded)) {
        return false;
      }
      const hub = LAYERS_ADD_REGISTRY.find(
        (row) => row.id === layer.id && row.isSpatialHub,
      );
      if (hub && !visibleHub.has(layer.id)) return false;
      return true;
    }),
  }));
}

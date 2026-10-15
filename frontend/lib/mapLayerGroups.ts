/**
 * Map layers drawer groups — derived from the live layer registry.
 * Live switches only; deferred layers live on /roadmap (MAP-CARDS E7).
 */

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
  };
}

/** Curated live drawer layers — paint keys match ScotlandMap toggles. */
export const MAP_DRAWER_LAYERS: MapDrawerLayer[] =
  MAP_LAYER_REGISTRY.map(toDrawerLayer);

export function mapDrawerLayersByGroup(): Array<{
  key: MapLayerGroupKey;
  label: string;
  layers: MapDrawerLayer[];
}> {
  return MAP_LAYER_GROUP_ORDER.map((key) => ({
    key,
    label: mapLayerGroupLabel(key),
    layers: MAP_DRAWER_LAYERS.filter((layer) => layer.group === key),
  }));
}

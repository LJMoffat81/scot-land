"use client";

import { Fragment, useEffect, useState, type ReactNode } from "react";
import ConfidenceTag from "@/components/ConfidenceTag";
import MapRangeLegend from "@/components/MapRangeLegend";
import {
  buildInlineLegendFromRegistry,
  getMapLayer,
  manifestLegendsForDrawerLayer,
  MAP_LAYER_GROUP_NOTES,
  TENURE_LABEL,
  type InlineLegendView,
  type MapLayerGroupKey,
  type MapLayerLegendClass,
} from "@/lib/mapLayerRegistry";
import {
  mapDrawerLayersByGroup,
  type MapDrawerLayer,
} from "@/lib/mapLayerGroups";
import { popDensityLegendProps } from "@/lib/popDensityLegend";

const LAND_HEADER = "LAND";
const LAND_SUBTITLE = "Everything nature provides and no one made";
const PLACES_HEADER = "PLACES AND BOUNDARIES";

/** Display-only Limits group — registry `group` keys stay unchanged. */
export const LIMITS_ON_USE_LAYER_IDS = [
  "flood",
  "contaminated_land",
  "designations",
  "crofting",
] as const;

export const LIMITS_ON_USE_LABEL = "Limits on use";

export const LIMITS_ON_USE_NOTE =
  "These can limit what land is used for. They add no value and are not a rent.";

const LIMITS_ON_USE_ID_SET: ReadonlySet<string> = new Set(
  LIMITS_ON_USE_LAYER_IDS,
);

type LandSubgroupKey = "land" | "tenure" | "resources" | "nature";

type DrawerGroupKey = MapLayerGroupKey | "limits";

const LAND_SUBGROUP_LABEL: Record<LandSubgroupKey, string> = {
  land: "Sites",
  tenure: TENURE_LABEL,
  resources: "Natural resources",
  nature: "Nature",
};

const LAND_SUBGROUP_ORDER: readonly LandSubgroupKey[] = [
  "land",
  "tenure",
  "resources",
  "nature",
];

export type MapLayerToggleState = Record<string, boolean>;

export type MapLayersDrawerProps = {
  enabled?: MapLayerToggleState;
  onEnabledChange?: (next: MapLayerToggleState) => void;
  /**
   * Layer ids to omit from the panel (tiles unavailable / not ingested).
   * Unavailable layers are not listed at all (roadmap handles deferred layers).
   */
  unavailableIds?: ReadonlySet<string> | ReadonlyArray<string>;
  /**
   * Improvement Service extracts present in the tile manifest.
   * Null or omitted hides those rows (skip when the extract is absent).
   */
  spatialHubPresent?: Record<string, boolean> | null;
  /** True when sepa_flood_dz has rows. The flood switch stays hidden until then. */
  floodDzLoaded?: boolean;
  floodKind?: "river" | "coastal" | "surface";
  onFloodKindChange?: (kind: "river" | "coastal" | "surface") => void;
  /** Current map zoom for inline legend zoom gates. */
  mapZoom?: number;
  /**
   * People/km² fill ready (councils on, AGR off, context loaded).
   * When true, show the NRS key row under Council areas (SW-086).
   */
  popDensityKeyVisible?: boolean;
  /** Close control — parent owns open state (opening must not change layers). */
  onClose?: () => void;
  className?: string;
  title?: string;
  /**
   * SRC-C C3 — per drawer-layer-id as-of date strings (e.g. "1 Oct 2026"),
   * already parsed from the tile manifest version.
   */
  tileAsOf?: Record<string, string>;
  /**
   * ARCH-5a — tileset id → legend classes from the tile manifest.
   */
  tileLegends?: Readonly<
    Record<string, readonly { label: string; color: string }[]>
  >;
};

function asUnavailableSet(
  unavailableIds?: ReadonlySet<string> | ReadonlyArray<string>,
): Set<string> {
  if (!unavailableIds) return new Set();
  if (unavailableIds instanceof Set) return unavailableIds;
  return new Set(unavailableIds);
}

function chipLabel(
  tag: MapDrawerLayer["tag"],
): "Market" | "Modelled" | "Estimate" | null {
  if (tag === "market") return "Market";
  if (tag === "proxy") return "Modelled";
  if (tag === "shadow") return "Estimate";
  return null;
}

function initialOpenGroups(
  groups: ReadonlyArray<{
    key: DrawerGroupKey;
    layers: ReadonlyArray<{ id: string }>;
  }>,
  enabled: MapLayerToggleState,
): Set<DrawerGroupKey> {
  const open = new Set<DrawerGroupKey>();
  for (const { key, layers } of groups) {
    if (layers.some((layer) => Boolean(enabled[layer.id]))) {
      open.add(key);
    }
  }
  return open;
}

function layersForLandSubgroup(
  groups: ReadonlyArray<{
    key: MapLayerGroupKey;
    layers: ReadonlyArray<MapDrawerLayer>;
  }>,
  key: LandSubgroupKey,
): MapDrawerLayer[] {
  const group = groups.find((entry) => entry.key === key);
  return (group?.layers ?? []).filter(
    (layer) => !LIMITS_ON_USE_ID_SET.has(layer.id),
  );
}

function limitsOnUseLayers(
  groups: ReadonlyArray<{
    key: MapLayerGroupKey;
    layers: ReadonlyArray<MapDrawerLayer>;
  }>,
): MapDrawerLayer[] {
  const byId = new Map<string, MapDrawerLayer>();
  for (const { layers } of groups) {
    for (const layer of layers) {
      if (LIMITS_ON_USE_ID_SET.has(layer.id)) byId.set(layer.id, layer);
    }
  }
  return LIMITS_ON_USE_LAYER_IDS.map((id) => byId.get(id)).filter(
    (layer): layer is MapDrawerLayer => Boolean(layer),
  );
}

/**
 * Map layers drawer — themed accordion groups with inline legends.
 * Opening the panel never changes layer toggle state.
 */
export default function MapLayersDrawer({
  enabled = {},
  onEnabledChange,
  unavailableIds,
  spatialHubPresent = null,
  floodDzLoaded = false,
  floodKind = "river",
  onFloodKindChange,
  mapZoom,
  popDensityKeyVisible = false,
  onClose,
  className,
  title = "Map layers",
  tileAsOf,
  tileLegends,
}: MapLayersDrawerProps) {
  const unavailable = asUnavailableSet(unavailableIds);
  const groups = mapDrawerLayersByGroup({
    spatialHubPresent,
    floodLoaded: floodDzLoaded,
  }).map(({ key, layers }) => ({
      key,
      layers: layers.filter((layer) => !unavailable.has(layer.id)),
    }),
  );

  const limitsLayers = limitsOnUseLayers(groups);
  const landSubgroups = LAND_SUBGROUP_ORDER.map((key) => ({
    key,
    layers: layersForLandSubgroup(groups, key),
  })).filter((entry) => entry.layers.length > 0);

  const drawerGroupsForOpen: ReadonlyArray<{
    key: DrawerGroupKey;
    layers: ReadonlyArray<{ id: string }>;
  }> = [
    ...landSubgroups,
    ...(limitsLayers.length > 0
      ? [{ key: "limits" as const, layers: limitsLayers }]
      : []),
    {
      key: "places",
      layers: groups.find((entry) => entry.key === "places")?.layers ?? [],
    },
  ];

  const [openGroups, setOpenGroups] = useState<Set<DrawerGroupKey>>(() =>
    initialOpenGroups(drawerGroupsForOpen, enabled),
  );

  // Stable serialization — groups is rebuilt each render; only reopen when an
  // enabled layer appears (GBP-LIVE / default boot). §3.4: group with an
  // active layer starts open.
  const enabledGroupKeys = drawerGroupsForOpen
    .filter(({ layers }) => layers.some((layer) => Boolean(enabled[layer.id])))
    .map(({ key }) => key)
    .join(",");

  useEffect(() => {
    if (!enabledGroupKeys) return;
    const keys = enabledGroupKeys.split(",") as DrawerGroupKey[];
    setOpenGroups((prev) => {
      const next = new Set(prev);
      let changed = false;
      for (const key of keys) {
        if (!next.has(key)) {
          next.add(key);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [enabledGroupKeys]);

  const placesLayers =
    groups.find((entry) => entry.key === "places")?.layers ?? [];

  const setEnabled = (id: string, on: boolean) => {
    onEnabledChange?.({ ...enabled, [id]: on });
  };

  const toggleGroup = (key: DrawerGroupKey) => {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div
      className={["map-layers-drawer", "layers-panel", className]
        .filter(Boolean)
        .join(" ")}
      data-testid="layers-panel"
      data-drawer="map-layers"
    >
      <div className="layers-panel-header">
        <p className="hud-tools-title">{title}</p>
        {onClose ? (
          <button
            type="button"
            className="layers-panel-close"
            aria-label="Close map layers"
            data-testid="layers-panel-close"
            onClick={onClose}
          >
            ×
          </button>
        ) : null}
      </div>

      <p className="layer-meta" data-testid="map-layers-labels-link">
        <a href="/methodology#glossary-tags">What the labels mean</a>
      </p>

      <section data-testid="layers-nav-land">
        <p className="layers-nav-header" data-testid="layers-nav-header">
          {LAND_HEADER}
        </p>
        <p className="layers-nav-subtitle" data-testid="layers-nav-land-subtitle">
          {LAND_SUBTITLE}
        </p>
        {landSubgroups.map(({ key, layers }) => (
          <LayersAccordion
            key={key}
            groupKey={key}
            label={LAND_SUBGROUP_LABEL[key]}
            subgroup
            expanded={openGroups.has(key)}
            onToggle={() => toggleGroup(key)}
            note={MAP_LAYER_GROUP_NOTES[key]}
          >
            {layers.map((layer) => (
              <DrawerLayerRow
                key={layer.id}
                layer={layer}
                on={Boolean(enabled[layer.id])}
                mapZoom={mapZoom}
                floodKind={floodKind}
                onFloodKindChange={onFloodKindChange}
                onToggle={() => setEnabled(layer.id, !enabled[layer.id])}
                asOfDate={tileAsOf?.[layer.id]}
                manifestClasses={manifestLegendsForDrawerLayer(
                  layer.id,
                  tileLegends,
                )}
              />
            ))}
          </LayersAccordion>
        ))}
        {limitsLayers.length > 0 ? (
          <LayersAccordion
            groupKey="limits"
            label={LIMITS_ON_USE_LABEL}
            subgroup
            expanded={openGroups.has("limits")}
            onToggle={() => toggleGroup("limits")}
            note={LIMITS_ON_USE_NOTE}
          >
            {limitsLayers.map((layer) => (
              <DrawerLayerRow
                key={layer.id}
                layer={layer}
                on={Boolean(enabled[layer.id])}
                mapZoom={mapZoom}
                floodKind={floodKind}
                onFloodKindChange={onFloodKindChange}
                onToggle={() => setEnabled(layer.id, !enabled[layer.id])}
                asOfDate={tileAsOf?.[layer.id]}
                manifestClasses={manifestLegendsForDrawerLayer(
                  layer.id,
                  tileLegends,
                )}
              />
            ))}
          </LayersAccordion>
        ) : null}
      </section>

      <section data-testid="layers-nav-places">
        <LayersAccordion
          groupKey="places"
          label={PLACES_HEADER}
          header
          expanded={openGroups.has("places")}
          onToggle={() => toggleGroup("places")}
          note={MAP_LAYER_GROUP_NOTES.places}
        >
          {placesLayers.map((layer) => {
            const densityKey =
              layer.id === "councils" && popDensityKeyVisible
                ? popDensityLegendProps()
                : null;
            return (
              <Fragment key={layer.id}>
                <DrawerLayerRow
                  layer={layer}
                  on={Boolean(enabled[layer.id])}
                  mapZoom={mapZoom}
                  onToggle={() => setEnabled(layer.id, !enabled[layer.id])}
                  asOfDate={tileAsOf?.[layer.id]}
                  manifestClasses={manifestLegendsForDrawerLayer(
                    layer.id,
                    tileLegends,
                  )}
                />
                {densityKey ? (
                  <li
                    className="layers-panel-row"
                    data-testid="map-layer-pop-density-key"
                  >
                    <MapRangeLegend
                      title={densityKey.title}
                      ranges={densityKey.ranges}
                      showNoData={densityKey.showNoData}
                      mode={densityKey.mode}
                      layerId={densityKey.layerId}
                      source={densityKey.source}
                    />
                  </li>
                ) : null}
              </Fragment>
            );
          })}
        </LayersAccordion>
      </section>

      <div className="layers-panel-footer">
        <p className="layer-meta" data-testid="map-layers-roadmap-link">
          <a href="/roadmap#map-layers">{"What's coming next →"}</a>
        </p>
        <p className="layer-meta" data-testid="map-layers-sources-licences">
          <a href="/data#licences">Sources and licences →</a>
        </p>
      </div>
    </div>
  );
}

function LayersAccordion({
  groupKey,
  label,
  expanded,
  onToggle,
  subgroup,
  header,
  note,
  children,
}: {
  groupKey: DrawerGroupKey;
  label: string;
  expanded: boolean;
  onToggle: () => void;
  subgroup?: boolean;
  header?: boolean;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section
      className="layers-panel-group"
      aria-label={label}
      data-testid={`layers-group-${groupKey}`}
    >
      <button
        type="button"
        className="layers-panel-accordion"
        aria-expanded={expanded}
        data-testid={`layers-group-toggle-${groupKey}`}
        onClick={onToggle}
      >
        <span
          className={
            header
              ? "layer-select-label layers-nav-header"
              : "layers-nav-subgroup"
          }
          data-testid={
            header ? "layers-nav-header" : subgroup ? "layers-nav-subgroup" : undefined
          }
        >
          {label}
        </span>
        <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
      </button>
      {note ? (
        <p
          className="layer-meta layers-nav-note"
          data-testid={
            groupKey === "nature"
              ? "layers-nature-note"
              : `layers-group-note-${groupKey}`
          }
        >
          {note}
        </p>
      ) : null}
      {expanded ? <ul className="layers-panel-list">{children}</ul> : null}
    </section>
  );
}

const FLOOD_KINDS = [
  { id: "river", label: "River" },
  { id: "coastal", label: "Coastal" },
  { id: "surface", label: "Surface water" },
] as const;

function DrawerLayerRow({
  layer,
  on,
  onToggle,
  mapZoom,
  floodKind,
  onFloodKindChange,
  asOfDate,
  manifestClasses,
}: {
  layer: MapDrawerLayer;
  on: boolean;
  onToggle: () => void;
  mapZoom?: number;
  floodKind?: "river" | "coastal" | "surface";
  onFloodKindChange?: (kind: "river" | "coastal" | "surface") => void;
  asOfDate?: string;
  manifestClasses?: readonly MapLayerLegendClass[] | null;
}) {
  const registry = getMapLayer(layer.id);
  const legend: InlineLegendView | null =
    on && registry
      ? buildInlineLegendFromRegistry(registry, { mapZoom, manifestClasses })
      : null;
  const badge = legend ? chipLabel(legend.chip) : null;

  return (
    <li
      className="layers-panel-row"
      data-testid={`map-layer-${layer.id}`}
      data-coming-soon="false"
      data-minzoom={registry?.minzoom ?? layer.minzoom}
      data-maxzoom={registry?.maxzoom ?? layer.maxzoom}
      data-zoom-out-above={
        registry?.zoomOutAbove != null ? String(registry.zoomOutAbove) : ""
      }
      data-paint-layers={(registry?.paintLayerIds ?? []).join(" ")}
    >
      <button
        type="button"
        role="switch"
        className="layers-panel-switch"
        data-testid={`layer-toggle-${layer.id}`}
        aria-checked={on}
        aria-label={layer.label}
        aria-describedby={
          layer.subline ? `layer-desc-${layer.id}` : undefined
        }
        onClick={onToggle}
      >
        <span className="layers-panel-switch-label">{layer.label}</span>
        <span
          className={
            on ? "layers-panel-switch-track on" : "layers-panel-switch-track"
          }
          aria-hidden="true"
        />
      </button>
      {layer.id === "flood" && onFloodKindChange ? (
        <div
          className="flood-kind"
          role="radiogroup"
          aria-label="Flood source"
          data-testid="flood-kind"
        >
          {FLOOD_KINDS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="radio"
              className="flood-kind-option"
              aria-checked={floodKind === item.id}
              data-testid={`flood-kind-${item.id}`}
              onClick={() => onFloodKindChange(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
      {layer.subline ? (
        <p
          id={`layer-desc-${layer.id}`}
          className="layer-meta"
          data-testid={`layer-desc-${layer.id}`}
        >
          {layer.subline}
        </p>
      ) : null}

      {legend ? (
        <div
          className="layers-inline-legend"
          data-testid={`layer-inline-legend-${layer.id}`}
        >
          {badge ? (
            <div className="layers-inline-legend-chip">
              <ConfidenceTag kind={legend.chip!} />
            </div>
          ) : null}
          {legend.nonCommercial ? (
            <p
              className="layer-meta"
              data-testid={`layer-non-commercial-${layer.id}`}
            >
              Non-commercial
            </p>
          ) : null}
          {legend.zoomGated ? (
            <p
              className="layer-meta"
              data-testid={`layer-zoom-gate-${layer.id}`}
              aria-live="polite"
            >
              {legend.zoomHint}
            </p>
          ) : legend.zoomOut && legend.zoomOutHint ? (
            <p
              className="layer-meta"
              data-testid={`layer-zoom-gate-${layer.id}`}
              aria-live="polite"
            >
              {legend.zoomOutHint}
            </p>
          ) : null}
          {/* Class key stays visible while zoom-gated so toggles still show Vacant/Derelict etc. */}
          {legend.rampScale ? (
            <p className="layers-inline-legend-scale">{legend.rampScale}</p>
          ) : null}
          {registry?.legendNote ? (
            <p className="layer-meta" data-testid="layer-flood-extent-legend">
              {registry.legendNote}
            </p>
          ) : null}
          <ul className="layer-legend" aria-label={`${layer.label} key`}>
            {legend.classes.map((row) => (
              <li key={`${layer.id}-${row.label}-${row.color}`}>
                <span
                  className={
                    row.striped
                      ? "layer-legend-swatch striped"
                      : "layer-legend-swatch"
                  }
                  style={{ backgroundColor: row.color }}
                />
                <span>{row.label}</span>
              </li>
            ))}
          </ul>
          <p
            className="layer-meta layers-source-caption"
            data-testid={`layer-source-caption-${layer.id}`}
          >
            {legend.sourceCaption}
            {asOfDate ? (
              <span data-testid={`layer-asof-${layer.id}`}>
                {` · Data as of ${asOfDate}`}
              </span>
            ) : null}
          </p>
        </div>
      ) : null}
    </li>
  );
}

"use client";

import { useEffect, useState, type ReactNode } from "react";
import ConfidenceTag from "@/components/ConfidenceTag";
import {
  aimStatusPanelTag,
  layersPanelAimRows,
  type AimGroupId,
  type AimRow,
} from "@/lib/aimToCover";
import {
  buildInlineLegendFromRegistry,
  getMapLayer,
  type InlineLegendView,
  type MapLayerGroupKey,
} from "@/lib/mapLayerRegistry";
import {
  mapDrawerLayersByGroup,
  type MapDrawerLayer,
} from "@/lib/mapLayerGroups";

const LAND_HEADER = "LAND";
const LAND_SUBTITLE = "Everything nature provides and no one made";
const PLACES_HEADER = "PLACES AND BOUNDARIES";
const SERVICES_OF_NATURE_NOTE = "Estimates only. Never taxed.";

const LAND_SUBGROUP_LABEL: Record<AimGroupId, string> = {
  land: "Sites",
  resources: "Natural resources",
  nature: "Services of nature",
};

const LAND_SUBGROUP_ORDER: readonly AimGroupId[] = [
  "land",
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
  /** Current map zoom for inline legend zoom gates. */
  mapZoom?: number;
  /** Close control — parent owns open state (opening must not change layers). */
  onClose?: () => void;
  className?: string;
  title?: string;
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
  groups: ReturnType<typeof mapDrawerLayersByGroup>,
  enabled: MapLayerToggleState,
): Set<MapLayerGroupKey> {
  const open = new Set<MapLayerGroupKey>();
  for (const { key, layers } of groups) {
    if (layers.some((layer) => Boolean(enabled[layer.id]))) {
      open.add(key);
    }
  }
  return open;
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
  mapZoom,
  onClose,
  className,
  title = "Map layers",
}: MapLayersDrawerProps) {
  const unavailable = asUnavailableSet(unavailableIds);
  const groups = mapDrawerLayersByGroup({ spatialHubPresent }).map(
    ({ key, layers }) => ({
      key,
      layers: layers.filter((layer) => !unavailable.has(layer.id)),
    }),
  );

  const [openGroups, setOpenGroups] = useState<Set<MapLayerGroupKey>>(() =>
    initialOpenGroups(groups, enabled),
  );

  // Stable serialization — groups is rebuilt each render; only reopen when an
  // enabled layer appears (GBP-LIVE / default boot). §3.4: group with an
  // active layer starts open.
  const enabledGroupKeys = groups
    .filter(({ layers }) => layers.some((layer) => Boolean(enabled[layer.id])))
    .map(({ key }) => key)
    .join(",");

  useEffect(() => {
    if (!enabledGroupKeys) return;
    const keys = enabledGroupKeys.split(",") as MapLayerGroupKey[];
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

  const toggleGroup = (key: MapLayerGroupKey) => {
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
        {LAND_SUBGROUP_ORDER.map((key) => {
          const group = groups.find((entry) => entry.key === key);
          const layers = group?.layers ?? [];
          return (
            <LayersAccordion
              key={key}
              groupKey={key}
              label={LAND_SUBGROUP_LABEL[key]}
              subgroup
              expanded={openGroups.has(key)}
              onToggle={() => toggleGroup(key)}
              note={key === "nature" ? SERVICES_OF_NATURE_NOTE : undefined}
            >
              {layers.map((layer) => (
                <DrawerLayerRow
                  key={layer.id}
                  layer={layer}
                  on={Boolean(enabled[layer.id])}
                  mapZoom={mapZoom}
                  onToggle={() => setEnabled(layer.id, !enabled[layer.id])}
                />
              ))}
              {placeholdersFor(key, layers).map((row) => (
                <AimPlaceholder key={row.id} row={row} />
              ))}
            </LayersAccordion>
          );
        })}
        <p
          className="layer-meta layers-limits-explainer"
          data-testid="map-layers-limits-explainer"
        >
          <strong>Limits on use</strong>
          {" — "}
          Protected nature sites, flood risk and crofting change best use and
          add no value. They are not a rent.
        </p>
      </section>

      <section data-testid="layers-nav-places">
        <LayersAccordion
          groupKey="places"
          label={PLACES_HEADER}
          header
          expanded={openGroups.has("places")}
          onToggle={() => toggleGroup("places")}
        >
          {placesLayers.map((layer) => (
            <DrawerLayerRow
              key={layer.id}
              layer={layer}
              on={Boolean(enabled[layer.id])}
              mapZoom={mapZoom}
              onToggle={() => setEnabled(layer.id, !enabled[layer.id])}
            />
          ))}
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

function placeholdersFor(
  groupKey: AimGroupId,
  layers: readonly MapDrawerLayer[],
): readonly AimRow[] {
  const liveLabels = new Set(layers.map((layer) => layer.label));
  return layersPanelAimRows(groupKey).filter((row) => !liveLabels.has(row.name));
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
  groupKey: MapLayerGroupKey;
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
            header ? "layer-select-label layers-nav-header" : "layer-select-label"
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
        <p className="layer-meta layers-nav-note" data-testid="layers-nature-note">
          {note}
        </p>
      ) : null}
      {expanded ? <ul className="layers-panel-list">{children}</ul> : null}
    </section>
  );
}

function AimPlaceholder({ row }: { row: AimRow }) {
  return (
    <li
      className="layers-panel-row layers-aim-placeholder"
      data-testid={`layers-aim-${row.id}`}
      data-aim-name={row.name}
      aria-disabled="true"
    >
      <span className="layers-aim-name">{row.name}</span>
      <span className="layers-aim-tag" data-testid={`layers-aim-tag-${row.id}`}>
        {aimStatusPanelTag(row.status)}
      </span>
      <a
        className="layers-aim-link"
        href={`/roadmap#${row.id}`}
        data-testid={`layers-aim-link-${row.id}`}
      >
        Roadmap
      </a>
    </li>
  );
}

function DrawerLayerRow({
  layer,
  on,
  onToggle,
  mapZoom,
}: {
  layer: MapDrawerLayer;
  on: boolean;
  onToggle: () => void;
  mapZoom?: number;
}) {
  const registry = getMapLayer(layer.id);
  const legend: InlineLegendView | null =
    on && registry
      ? buildInlineLegendFromRegistry(registry, { mapZoom })
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
          </p>
        </div>
      ) : null}
    </li>
  );
}

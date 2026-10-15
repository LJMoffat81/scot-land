"use client";

import { useEffect, useState } from "react";
import ConfidenceTag from "@/components/ConfidenceTag";
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

export type MapLayerToggleState = Record<string, boolean>;

export type MapLayersDrawerProps = {
  enabled?: MapLayerToggleState;
  onEnabledChange?: (next: MapLayerToggleState) => void;
  /**
   * Layer ids to omit from the panel (tiles unavailable / not ingested).
   * Unavailable layers are not listed at all (roadmap handles deferred layers).
   */
  unavailableIds?: ReadonlySet<string> | ReadonlyArray<string>;
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
  mapZoom,
  onClose,
  className,
  title = "Map layers",
}: MapLayersDrawerProps) {
  const unavailable = asUnavailableSet(unavailableIds);
  const groups = mapDrawerLayersByGroup()
    .map(({ key, label, layers }) => ({
      key,
      label,
      layers: layers.filter((layer) => !unavailable.has(layer.id)),
    }))
    .filter(({ layers }) => layers.length > 0);

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

      {groups.map(({ key, label, layers }) => {
        const expanded = openGroups.has(key);
        return (
          <section
            key={key}
            className="layers-panel-group"
            aria-label={label}
            data-testid={`layers-group-${key}`}
          >
            <button
              type="button"
              className="layers-panel-accordion"
              aria-expanded={expanded}
              data-testid={`layers-group-toggle-${key}`}
              onClick={() => toggleGroup(key)}
            >
              <span className="layer-select-label">{label}</span>
              <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
            </button>
            {expanded ? (
              <ul className="layers-panel-list">
                {layers.map((layer) => {
                  const on = Boolean(enabled[layer.id]);
                  return (
                    <DrawerLayerRow
                      key={layer.id}
                      layer={layer}
                      on={on}
                      mapZoom={mapZoom}
                      onToggle={() => setEnabled(layer.id, !enabled[layer.id])}
                    />
                  );
                })}
              </ul>
            ) : null}
          </section>
        );
      })}

      <div className="layers-panel-footer">
        <p className="layer-meta" data-testid="map-layers-roadmap-link">
          <a href="/roadmap#map-layers">{"What's coming next →"}</a>
        </p>
        <p className="layer-meta" data-testid="map-layers-sources-licences">
          <a href="/data#licences">Sources and licences →</a>
        </p>
        <p
          className="layer-meta layers-limits-explainer"
          data-testid="map-layers-limits-explainer"
        >
          <strong>Limits on use</strong>
          {" — "}
          Protected nature sites, flood risk and crofting change best use and
          add no value. They are not a rent.
        </p>
      </div>
    </div>
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
    >
      <button
        type="button"
        role="switch"
        className="layers-panel-switch"
        data-testid={`layer-toggle-${layer.id}`}
        aria-checked={on}
        aria-label={layer.label}
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
            >
              {legend.zoomHint}
            </p>
          ) : (
            <>
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
            </>
          )}
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

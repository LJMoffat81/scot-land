"use client";

import ConfidenceTag from "@/components/ConfidenceTag";
import {
  mapDrawerLayersByGroup,
  type MapDrawerLayer,
} from "@/lib/mapLayerGroups";

export type MapLayerToggleState = Record<string, boolean>;

export type MapLayersDrawerProps = {
  enabled?: MapLayerToggleState;
  onEnabledChange?: (next: MapLayerToggleState) => void;
  /**
   * Layer ids forced to Coming soon / disabled (tiles unavailable or catalogue
   * not ingested). Merged with static comingSoon on the curated row.
   */
  unavailableIds?: ReadonlySet<string> | ReadonlyArray<string>;
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

/**
 * Right-side map layers drawer — Land / Natural resource rents / Services of
 * nature / Limits / Boundaries. Licence text lives in the map (i) and /data
 * (SW-044); chip key lives in the left legend only.
 */
export default function MapLayersDrawer({
  enabled = {},
  onEnabledChange,
  unavailableIds,
  className,
  title = "Layers",
}: MapLayersDrawerProps) {
  const groups = mapDrawerLayersByGroup();
  const unavailable = asUnavailableSet(unavailableIds);

  const setEnabled = (id: string, on: boolean) => {
    onEnabledChange?.({ ...enabled, [id]: on });
  };

  // Outer ScotlandMap shell already exposes complementary "Map layers".
  // Keep this a plain panel (not a second landmark) so names stay unique.
  return (
    <div
      className={["map-layers-drawer", "layers-panel", className]
        .filter(Boolean)
        .join(" ")}
      data-testid="layers-panel"
      data-drawer="map-layers"
    >
      <p className="hud-tools-title">{title}</p>

      {groups.map(({ key, label, layers }) => (
        <section
          key={key}
          className="layers-panel-group"
          aria-label={label}
          data-testid={`layers-group-${key}`}
        >
          <label className="layer-select-label">{label}</label>
          <ul className="layers-panel-list">
            {layers.map((layer) => {
              const comingSoon =
                Boolean(layer.comingSoon) || unavailable.has(layer.id);
              return (
                <DrawerLayerRow
                  key={layer.id}
                  layer={layer}
                  comingSoon={comingSoon}
                  on={Boolean(enabled[layer.id]) && !comingSoon}
                  onToggle={() => {
                    if (comingSoon) return;
                    setEnabled(layer.id, !enabled[layer.id]);
                  }}
                />
              );
            })}
          </ul>
        </section>
      ))}

      <p className="layer-meta" data-testid="map-layers-methodology-link">
        Full breakdown table and definitions:{" "}
        <a href="/methodology#calculation">How we value land</a>
      </p>
    </div>
  );
}

function DrawerLayerRow({
  layer,
  on,
  onToggle,
  comingSoon,
}: {
  layer: MapDrawerLayer;
  on: boolean;
  onToggle: () => void;
  comingSoon: boolean;
}) {
  return (
    <li
      className="layers-panel-row"
      data-testid={`map-layer-${layer.id}`}
      data-coming-soon={comingSoon ? "true" : "false"}
    >
      <div className="layers-panel-row-head">
        <button
          type="button"
          className={on ? "chip active" : "chip"}
          data-testid={`layer-toggle-${layer.id}`}
          aria-pressed={on}
          disabled={comingSoon}
          title={layer.description}
          onClick={onToggle}
        >
          {layer.label}
        </button>
        {layer.tag ? <ConfidenceTag kind={layer.tag} /> : null}
        {layer.group === "limits" ? (
          <span
            className="layers-panel-status tone-other"
            data-testid={`layer-tag-${layer.id}`}
          >
            Limit
          </span>
        ) : null}
        {comingSoon ? (
          <span
            className="layers-panel-status tone-gap"
            data-testid={`layer-coming-soon-${layer.id}`}
          >
            Coming soon
          </span>
        ) : null}
        <a
          className="layers-panel-info"
          href={`/data#${encodeURIComponent(layer.id)}`}
          aria-label={`Source and licence for ${layer.label}`}
          title="Source and licence"
          data-testid={`layer-info-${layer.id}`}
        >
          i
        </a>
      </div>
      <p
        className="layer-meta"
        data-testid={
          comingSoon
            ? `layer-coming-soon-line-${layer.id}`
            : `layer-desc-${layer.id}`
        }
      >
        {layer.description}
      </p>
    </li>
  );
}

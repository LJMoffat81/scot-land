"use client";

import ConfidenceTag from "@/components/ConfidenceTag";
import EvidenceTagLegend from "@/components/EvidenceTagLegend";
import {
  mapDrawerLayersByGroup,
  type MapDrawerLayer,
} from "@/lib/mapLayerGroups";

export type MapLayerToggleState = Record<string, boolean>;

export type MapLayersDrawerProps = {
  enabled?: MapLayerToggleState;
  onEnabledChange?: (next: MapLayerToggleState) => void;
  className?: string;
  title?: string;
};

/**
 * Right-side map layers drawer — Land / Resources / Nature / Limits / Boundaries.
 * Reuses existing ScotlandMap paint toggles via enabled ids.
 */
export default function MapLayersDrawer({
  enabled = {},
  onEnabledChange,
  className,
  title = "Layers",
}: MapLayersDrawerProps) {
  const groups = mapDrawerLayersByGroup();

  const setEnabled = (id: string, on: boolean) => {
    onEnabledChange?.({ ...enabled, [id]: on });
  };

  return (
    <aside
      className={["map-layers-drawer", "layers-panel", className]
        .filter(Boolean)
        .join(" ")}
      aria-label={title}
      data-testid="layers-panel"
      data-drawer="map-layers"
    >
      <p className="hud-tools-title">{title}</p>
      <p className="layer-meta">
        Toggle map layers. Figures for land value are being checked and are not
        published yet.
      </p>

      <EvidenceTagLegend compact />

      {groups.map(({ key, label, layers }) => (
        <section
          key={key}
          className="layers-panel-group"
          aria-label={label}
          data-testid={`layers-group-${key}`}
        >
          <label className="layer-select-label">{label}</label>
          <ul className="layers-panel-list">
            {layers.map((layer) => (
              <DrawerLayerRow
                key={layer.id}
                layer={layer}
                on={Boolean(enabled[layer.id])}
                onToggle={() => {
                  if (layer.comingSoon) return;
                  setEnabled(layer.id, !enabled[layer.id]);
                }}
              />
            ))}
          </ul>
        </section>
      ))}

      <p className="layer-meta" data-testid="map-layers-methodology-link">
        Full ledger table and definitions:{" "}
        <a href="/methodology#ledger">How we value land</a>
      </p>
    </aside>
  );
}

function DrawerLayerRow({
  layer,
  on,
  onToggle,
}: {
  layer: MapDrawerLayer;
  on: boolean;
  onToggle: () => void;
}) {
  const comingSoon = Boolean(layer.comingSoon);
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
      </div>
      <p className="layer-meta">{layer.description}</p>
      <p className="layer-meta" data-testid={`layer-licence-${layer.id}`}>
        Licence:{" "}
        {layer.licenceUrl ? (
          <a href={layer.licenceUrl} target="_blank" rel="noopener noreferrer">
            {layer.licence}
          </a>
        ) : (
          layer.licence
        )}
      </p>
    </li>
  );
}

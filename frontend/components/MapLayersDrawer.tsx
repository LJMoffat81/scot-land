"use client";

import ConfidenceTag from "@/components/ConfidenceTag";
import EvidenceTagLegend from "@/components/EvidenceTagLegend";
import {
  DRAWER_OGL_V3,
  isOpenGovernmentLicenceDisplay,
  mapDrawerLicenceDisplay,
} from "@/lib/mapDrawerLicenceDisplay";
import {
  mapDrawerLayersByGroup,
  type MapDrawerLayer,
} from "@/lib/mapLayerGroups";

export type MapLayerToggleState = Record<string, boolean>;

export type MapLayersDrawerProps = {
  enabled?: MapLayerToggleState;
  onEnabledChange?: (next: MapLayerToggleState) => void;
  /**
   * Layer ids forced to Coming soon / disabled (tiles 503 or catalogue not
   * ingested). Merged with static `comingSoon` on the curated row.
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
 * nature / Limits / Boundaries. Reuses ScotlandMap paint toggles via enabled ids.
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
  // Chip key only while Market / Modelled / Estimate chips are on screen.
  const chipsOnScreen = groups.some(({ layers }) =>
    layers.some((layer) => Boolean(layer.tag)),
  );

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
      <p className="layer-meta">
        Toggle map layers. Figures for land value are being checked and are not
        published yet.
      </p>

      {chipsOnScreen ? <EvidenceTagLegend compact /> : null}

      {groups.map(({ key, label, layers }) => {
        const rows = layers.map((layer) => {
          const forced = unavailable.has(layer.id);
          return {
            layer,
            comingSoon: Boolean(layer.comingSoon) || forced,
          };
        });
        const showGroupOgl = rows.some(({ layer }) =>
          isOpenGovernmentLicenceDisplay(
            mapDrawerLicenceDisplay(
              layer.id,
              layer.licence,
              layer.licenceUrl,
            ),
          ),
        );
        return (
          <section
            key={key}
            className="layers-panel-group"
            aria-label={label}
            data-testid={`layers-group-${key}`}
          >
            <label className="layer-select-label">{label}</label>
            <ul className="layers-panel-list">
              {rows.map(({ layer, comingSoon }) => (
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
              ))}
            </ul>
            {showGroupOgl ? (
              <p
                className="layer-meta layers-group-ogl"
                data-testid={`layers-group-ogl-${key}`}
              >
                Licence:{" "}
                <a
                  href={DRAWER_OGL_V3.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {DRAWER_OGL_V3.label}
                </a>
              </p>
            ) : null}
          </section>
        );
      })}

      <p className="layer-meta" data-testid="map-layers-sources-licences">
        <a href="/data#licences">Sources and licences</a>
      </p>
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
  const display = mapDrawerLicenceDisplay(
    layer.id,
    layer.licence,
    layer.licenceUrl,
  );
  const showRowLicence = !isOpenGovernmentLicenceDisplay(display);
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
      {showRowLicence ? (
        <p className="layer-meta" data-testid={`layer-licence-${layer.id}`}>
          Licence:{" "}
          {display.url ? (
            <a href={display.url} target="_blank" rel="noopener noreferrer">
              {display.label}
            </a>
          ) : (
            display.label
          )}
        </p>
      ) : null}
    </li>
  );
}

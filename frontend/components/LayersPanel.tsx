"use client";

import { useEffect, useMemo, useState } from "react";

import { visitorFacingError } from "@/lib/api";
import {
  PUBLIC_WITHHELD_LAYER_IDS,
  UI_TOGGLE_LAYER_IDS,
  WITHHELD_PUBLIC_MESSAGE,
  fetchLayerCatalog,
  groupLabel,
  layerLicence,
  layerSourceLabel,
  type CatalogLayer,
  type LayerCatalog,
} from "@/lib/layerCatalog";

export type LayerToggleState = Record<string, boolean>;

export type LayersPanelProps = {
  /** Controlled toggle map (catalog id → on). Uncontrolled if omitted. */
  enabled?: LayerToggleState;
  defaultEnabled?: LayerToggleState;
  onEnabledChange?: (next: LayerToggleState) => void;
  /** Inject catalog (tests / Story). Otherwise fetches GET /layers/catalog. */
  catalog?: LayerCatalog | null;
  className?: string;
  title?: string;
};

function statusTone(status: string): string {
  if (status === "live") return "live";
  if (status === "linked") return "linked";
  if (status === "gap") return "gap";
  return "other";
}

function honestUnavailable(layer: CatalogLayer): string {
  if (PUBLIC_WITHHELD_LAYER_IDS.has(layer.id)) {
    return WITHHELD_PUBLIC_MESSAGE;
  }
  if (layer.status === "gap") {
    return (
      layer.description ||
      "Unavailable as an open map layer. The gap is shown; nothing is invented."
    );
  }
  if (layer.status === "linked") {
    return (
      layer.description ||
      "Linked to an official source. Not drawn on this map (no national open overlay)."
    );
  }
  return layer.description || "Not available on the map right now.";
}

export default function LayersPanel({
  enabled: controlled,
  defaultEnabled,
  onEnabledChange,
  catalog: catalogProp,
  className,
  title = "Layers & sources",
}: LayersPanelProps) {
  const [catalog, setCatalog] = useState<LayerCatalog | null>(
    catalogProp ?? null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(catalogProp == null);
  const [internalEnabled, setInternalEnabled] = useState<LayerToggleState>(
    () => defaultEnabled ?? {},
  );

  const enabled = controlled ?? internalEnabled;

  useEffect(() => {
    if (catalogProp !== undefined) {
      setCatalog(catalogProp);
      setLoading(false);
      setLoadError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchLayerCatalog()
      .then((payload) => {
        if (!cancelled) {
          setCatalog(payload);
          setLoadError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setCatalog(null);
          setLoadError(visitorFacingError(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [catalogProp]);

  const setEnabled = (id: string, on: boolean) => {
    const next = { ...enabled, [id]: on };
    if (controlled === undefined) setInternalEnabled(next);
    onEnabledChange?.(next);
  };

  const groups = useMemo(() => {
    const layers = catalog?.layers ?? [];
    const order = ["ownership", "spatial", "value"];
    const byGroup = new Map<string, CatalogLayer[]>();
    for (const layer of layers) {
      const key = layer.group || "other";
      const list = byGroup.get(key) ?? [];
      list.push(layer);
      byGroup.set(key, list);
    }
    const keys = [
      ...order.filter((g) => byGroup.has(g)),
      ...[...byGroup.keys()].filter((g) => !order.includes(g)).sort(),
    ];
    return keys.map((key) => ({ key, layers: byGroup.get(key) ?? [] }));
  }, [catalog]);

  const toggleSet = useMemo(() => new Set(UI_TOGGLE_LAYER_IDS), []);

  return (
    <aside
      className={["layers-panel", className].filter(Boolean).join(" ")}
      aria-label={title}
      data-testid="layers-panel"
    >
      <p className="hud-tools-title">{title}</p>
      <p className="layer-meta">
        Open layers from the platform catalog. Live layers can be toggled.
        Linked and gap rows stay honest — no invented geometry. Modelled plot
        AGR £ and tax scenarios are not shown here.
      </p>

      {loading && (
        <p className="layer-meta" data-testid="layers-panel-loading">
          Loading catalog…
        </p>
      )}
      {loadError && (
        <p className="error-line" data-testid="layers-panel-error">
          {loadError}
        </p>
      )}

      {!loading &&
        !loadError &&
        groups.map(({ key, layers }) => (
          <section
            key={key}
            className="layers-panel-group"
            aria-label={groupLabel(key)}
            data-testid={`layers-group-${key}`}
          >
            <label className="layer-select-label">{groupLabel(key)}</label>
            <ul className="layers-panel-list">
              {layers.map((layer) => {
                const isLive = layer.status === "live";
                const hasToggle = isLive && toggleSet.has(layer.id);
                const withheld = PUBLIC_WITHHELD_LAYER_IDS.has(layer.id);
                const on = Boolean(enabled[layer.id]);
                const sourceLabel = layerSourceLabel(layer);
                const licence = layerLicence(layer);
                const sourceHref = layer.source_url;

                return (
                  <li
                    key={layer.id}
                    className="layers-panel-row"
                    data-testid={`catalog-layer-${layer.id}`}
                    data-status={layer.status}
                  >
                    <div className="layers-panel-row-head">
                      {hasToggle ? (
                        <button
                          type="button"
                          className={on ? "chip active" : "chip"}
                          data-testid={`layer-toggle-${layer.id}`}
                          aria-pressed={on}
                          title={
                            withheld
                              ? WITHHELD_PUBLIC_MESSAGE
                              : layer.description || layer.label
                          }
                          onClick={() => setEnabled(layer.id, !on)}
                        >
                          {layer.label}
                        </button>
                      ) : (
                        <span
                          className="layers-panel-label"
                          data-testid={`layer-label-${layer.id}`}
                        >
                          {layer.label}
                        </span>
                      )}
                      <span
                        className={`layers-panel-status tone-${statusTone(String(layer.status))}`}
                        data-testid={`layer-status-${layer.id}`}
                      >
                        {layer.status}
                      </span>
                    </div>

                    {hasToggle && layer.description && (
                      <p className="layer-meta">{layer.description}</p>
                    )}

                    <p className="layer-meta" data-testid={`layer-source-${layer.id}`}>
                      Source:{" "}
                      {sourceHref ? (
                        <a
                          href={sourceHref}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {sourceLabel}
                        </a>
                      ) : (
                        sourceLabel
                      )}
                    </p>
                    {layer.attribution?.trim() ? (
                      <p
                        className="layer-meta"
                        data-testid={`layer-attribution-${layer.id}`}
                      >
                        {layer.attribution.trim()}
                      </p>
                    ) : null}
                    <p
                      className="layer-meta"
                      data-testid={`layer-licence-${layer.id}`}
                    >
                      Licence:{" "}
                      {layer.licence_url ? (
                        <a
                          href={layer.licence_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {licence}
                        </a>
                      ) : (
                        licence
                      )}
                    </p>

                    {hasToggle && withheld && on && (
                      <p
                        className="layers-panel-unavailable"
                        data-testid={`layer-unavailable-${layer.id}`}
                      >
                        {WITHHELD_PUBLIC_MESSAGE}
                      </p>
                    )}
                    {!hasToggle && (
                      <p
                        className="layers-panel-unavailable"
                        data-testid={`layer-unavailable-${layer.id}`}
                      >
                        {honestUnavailable(layer)}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
    </aside>
  );
}

/** Exported for drift scripts / tests — ids LayersPanel will toggle when live. */
export const LAYERS_PANEL_TOGGLE_IDS = UI_TOGGLE_LAYER_IDS;

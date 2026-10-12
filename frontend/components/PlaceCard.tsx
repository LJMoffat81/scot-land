"use client";

import {
  sanitizePlaceCard,
  type PlaceCardPayload,
  type PlaceLayer,
} from "../lib/placeCard";

export type PlaceCardProps = {
  data: PlaceCardPayload | null;
  isLoading?: boolean;
  error?: string | null;
  onClose?: () => void;
  /** When true, render as a floating HUD card (map shell). Default: true. */
  floating?: boolean;
};

function intersectsLabel(layer: PlaceLayer): string {
  if (layer.status === "gap") return "Gap";
  if (layer.status === "linked") return "Linked";
  if (layer.intersects === true) return "Intersects";
  if (layer.intersects === false) return "No hit";
  return "Unknown";
}

function intersectsClass(layer: PlaceLayer): string {
  if (layer.status === "gap") return "place-layer-gap";
  if (layer.status === "linked") return "place-layer-linked";
  if (layer.intersects === true) return "place-layer-hit";
  if (layer.intersects === false) return "place-layer-miss";
  return "place-layer-unknown";
}

export function PlaceCard({
  data,
  isLoading = false,
  error = null,
  onClose,
  floating = true,
}: PlaceCardProps) {
  const card = data ? sanitizePlaceCard(data) : null;
  const shellClass = floating
    ? "hud-card hud-place place-card"
    : "place-card place-card-standalone";

  const placeLine = [
    card?.postcode,
    card?.council_name,
    card ? `${card.lat.toFixed(5)}, ${card.lng.toFixed(5)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const zone = card?.data_zone;
  const zoneLine =
    zone?.status === "ok" && zone.code
      ? `Data zone ${zone.code}${zone.name ? `, ${zone.name}` : ""}${
          zone.vintage != null ? ` (${zone.vintage})` : ""
        }`
      : zone?.status === "miss"
        ? zone.note || "No data zone at this point."
        : zone?.status === "unavailable"
          ? zone.note || "Data zone lookup unavailable."
          : null;

  return (
    <aside
      className={shellClass}
      role="dialog"
      aria-label="Place card"
      data-testid="place-card"
    >
      {onClose ? (
        <button
          type="button"
          className="hud-close"
          onClick={onClose}
          aria-label="Close place card"
        >
          ×
        </button>
      ) : null}

      <header className="place-card-header">
        <p className="place-card-kicker">Place</p>
        <h2 className="place-card-title">
          {card?.council_name || card?.postcode || "Selected spot"}
        </h2>
        {placeLine ? <p className="place-card-meta">{placeLine}</p> : null}
        {zoneLine ? (
          <p className="place-card-meta" data-testid="place-card-data-zone">
            {zoneLine}
          </p>
        ) : null}
      </header>

      {isLoading ? (
        <div className="place-card-loading" aria-busy="true">
          Looking up this spot…
        </div>
      ) : null}

      {error ? (
        <p className="place-card-error" role="alert">
          {error}
        </p>
      ) : null}

      {!isLoading && !error && card ? (
        <div className="place-card-body">
          {card.vacant_or_derelict ? (
            <p className="place-flags">
              <span className="flag vacant">Vacant or derelict (survey)</span>
            </p>
          ) : null}

          <section aria-label="Layers at this spot">
            <h3 className="place-card-section">Layers at this spot</h3>
            <ul className="place-layer-list" data-testid="place-card-layers">
              {card.layers.map((layer) => (
                <li
                  key={layer.id}
                  className={`place-layer-row ${intersectsClass(layer)}`}
                  data-layer-id={layer.id}
                >
                  <div className="place-layer-top">
                    <span className="place-layer-label">{layer.label}</span>
                    <span className="place-layer-state">
                      {intersectsLabel(layer)}
                    </span>
                  </div>
                  {layer.note ? (
                    <p className="place-layer-note">{layer.note}</p>
                  ) : null}
                  {layer.id === "boundaries" &&
                  layer.intersects &&
                  card.parcel?.label ? (
                    <p className="place-layer-note">
                      Parcel {card.parcel.label}
                      {card.parcel.area_sqm != null
                        ? ` · ${Math.round(card.parcel.area_sqm).toLocaleString("en-GB")} m²`
                        : ""}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>

          <section aria-label="Links">
            <h3 className="place-card-section">Links</h3>
            <ul className="place-link-list" data-testid="place-card-links">
              {card.links.map((link) => {
                const external = /^https?:\/\//i.test(link.url);
                return (
                  <li key={link.id}>
                    <a
                      href={link.url}
                      {...(external
                        ? { target: "_blank", rel: "noreferrer" }
                        : {})}
                    >
                      {link.label}
                    </a>
                  </li>
                );
              })}
            </ul>
          </section>

          <p className="place-card-disclaimer">
            Ownership and survey context only. No modelled plot Annual Ground
            Rent on this card. Research map — not a title or a rates bill.
          </p>
        </div>
      ) : null}

      {!isLoading && !error && !card ? (
        <p className="place-card-empty">Click the map to look up a place.</p>
      ) : null}
    </aside>
  );
}

export default PlaceCard;

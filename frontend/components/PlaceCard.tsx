"use client";

import {
  PLACE_CARD_DATA_ZONE_GRAIN,
  PLACE_CARD_RENT_RANGE_TAGS,
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

function layerLicence(layer: PlaceLayer): string {
  return layer.licence?.trim() || "Licence not recorded";
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
        <p className="place-card-kicker">Annual Ground Rent</p>
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
          <section
            className="place-card-rent"
            aria-label="Annual Ground Rent ranges"
            data-testid="place-card-rent-ranges"
          >
            <h3 className="place-card-section">Annual Ground Rent</h3>
            <p className="place-card-rent-intro">
              Scot-LAND&apos;s purpose is Annual Ground Rent at this place.
              Rents appear only as ranges labelled market, proxy or shadow. £
              figures are not published yet while calibration is checked.
            </p>
            <ul className="place-rent-range-list">
              {PLACE_CARD_RENT_RANGE_TAGS.map((tag) => (
                <li
                  key={tag}
                  className={`place-rent-range-row tone-${tag}`}
                  data-testid={`place-card-rent-${tag}`}
                >
                  <span className={`place-stack-tag tone-${tag}`}>{tag}</span>
                  <span className="place-rent-range-label">not yet</span>
                </li>
              ))}
            </ul>
            <p
              className="place-card-grain"
              data-testid="place-card-data-zone-grain"
            >
              {PLACE_CARD_DATA_ZONE_GRAIN}
            </p>
          </section>

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
                  <p
                    className="place-layer-licence"
                    data-testid={`place-card-licence-${layer.id}`}
                  >
                    Licence:{" "}
                    {layer.licence_url ? (
                      <a
                        href={layer.licence_url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {layerLicence(layer)}
                      </a>
                    ) : (
                      layerLicence(layer)
                    )}
                  </p>
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
              {card.data_zone?.status === "ok" && card.data_zone.code ? (
                <li>
                  <a
                    href={`/place?zone=${encodeURIComponent(card.data_zone.code)}`}
                    data-testid="place-card-hectare-stack-link"
                  >
                    Per-hectare ledger stack
                  </a>
                </li>
              ) : null}
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

          <p className="place-card-disclaimer" data-testid="place-card-disclaimer">
            Ownership and survey context only. Research map — not a title or a
            rates bill. No £ Annual Ground Rent figures on this card.
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

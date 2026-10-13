"use client";

import {
  PLACE_CARD_CONSTRAINT_LABEL,
  PLACE_CARD_DATA_ZONE_GRAIN,
  PLACE_CARD_RESEARCH_DISCLAIMER,
  sanitizePlaceCard,
  type PlaceCardPayload,
  type PlaceLayer,
  type PlaceRentTag,
} from "../lib/placeCard";

export type PlaceCardProps = {
  data: PlaceCardPayload | null;
  isLoading?: boolean;
  error?: string | null;
  onClose?: () => void;
  /** When true, render as a floating HUD card (map shell). Default: true. */
  floating?: boolean;
  /** Extra class on the aside (e.g. place-card-stub for map HUD selectors). */
  className?: string;
};

function TagChip({ tag }: { tag: PlaceRentTag }) {
  const label =
    tag === "market" ? "Market" : tag === "proxy" ? "Proxy" : "Shadow";
  return (
    <span className={`place-tag tone-${tag}`} data-testid={`place-tag-${tag}`}>
      {label}
    </span>
  );
}

function layerLicence(layer: PlaceLayer): string {
  return layer.licence?.trim() || "Licence not recorded";
}

/**
 * Designer brief v3.1 place card — field order fixed.
 * Lives on the map; no £ figures.
 */
export function PlaceCard({
  data,
  isLoading = false,
  error = null,
  onClose,
  floating = true,
  className,
}: PlaceCardProps) {
  const card = data ? sanitizePlaceCard(data) : null;
  const shellClass = [
    floating ? "hud-card hud-place place-card" : "place-card place-card-standalone",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const zone = card?.data_zone;
  const dzCode =
    zone?.status === "ok" && zone.code
      ? zone.code
      : zone?.status === "miss"
        ? null
        : null;
  const iz = card?.intermediate_zone;
  const izDisplay =
    iz?.status === "ok" && iz.name
      ? iz.name
      : iz?.note || "No data";
  const placeName =
    card?.place_label?.trim() ||
    card?.postcode?.trim() ||
    zone?.name?.trim() ||
    "This place";

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
          {/* 1. Place */}
          <header className="place-card-header">
            <p className="place-card-kicker">Place</p>
            <h2 className="place-card-title" data-testid="place-card-place">
              {placeName}
            </h2>
            {card.postcode ? (
              <p className="place-card-meta">Postcode {card.postcode}</p>
            ) : null}
          </header>

          <dl className="place-card-fields">
            {/* 2. Data zone code (S01) */}
            <div className="place-card-field">
              <dt>Data zone</dt>
              <dd data-testid="place-card-data-zone">
                {dzCode ? (
                  <>
                    <span className="place-card-dz-code">{dzCode}</span>
                    {zone?.name ? (
                      <span className="place-card-meta-inline">
                        {" "}
                        · {zone.name}
                      </span>
                    ) : null}
                  </>
                ) : zone?.status === "miss" ? (
                  <span className="place-card-no-data">No data</span>
                ) : (
                  <span className="place-card-no-data">
                    {zone?.note || "No data"}
                  </span>
                )}
              </dd>
            </div>

            {/* 3. Intermediate Zone name */}
            <div className="place-card-field">
              <dt>Intermediate Zone</dt>
              <dd data-testid="place-card-intermediate-zone">
                {iz?.status === "ok" && iz.name ? (
                  iz.name
                ) : (
                  <span className="place-card-no-data">{izDisplay}</span>
                )}
                {iz?.code && iz.status !== "ok" ? (
                  <span className="place-card-meta-inline"> · {iz.code}</span>
                ) : null}
              </dd>
            </div>

            {/* 4. Council */}
            <div className="place-card-field">
              <dt>Council</dt>
              <dd data-testid="place-card-council">
                {card.council_name || (
                  <span className="place-card-no-data">No data</span>
                )}
              </dd>
            </div>

            {/* 5. Square reference */}
            <div className="place-card-field">
              <dt>Square reference</dt>
              <dd data-testid="place-card-square-reference">
                {card.square_reference}
              </dd>
            </div>
          </dl>

          {/* 6–7. AGR surface / resource / nature + of which notes */}
          <section
            className="place-card-agr"
            aria-label="Annual Ground Rent"
            data-testid="place-card-agr"
          >
            <h3 className="place-card-section">Annual Ground Rent</h3>
            <ul className="place-agr-list">
              {(card.agr_rows || []).map((row) => (
                <li
                  key={row.id}
                  className="place-agr-row"
                  data-testid={`place-card-agr-${row.id}`}
                >
                  <div className="place-agr-row-main">
                    <span className="place-agr-label">{row.label}</span>
                    <TagChip tag={row.tag} />
                    <span
                      className="place-agr-amount"
                      data-testid={`place-card-agr-amount-${row.id}`}
                    >
                      {row.amount_label}
                    </span>
                  </div>
                  {row.of_which?.length ? (
                    <ul className="place-agr-of-which">
                      {row.of_which.map((note) => (
                        <li
                          key={note.id}
                          data-testid={`place-card-of-which-${note.id}`}
                        >
                          {note.label}
                        </li>
                      ))}
                    </ul>
                  ) : null}
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

          {/* 8. Constraints (no £) */}
          <section
            className="place-card-constraints"
            aria-label="Constraints"
            data-testid="place-card-constraints"
          >
            <h3 className="place-card-section">Constraints</h3>
            <p className="place-card-constraint-banner">
              {PLACE_CARD_CONSTRAINT_LABEL}
            </p>
            <ul className="place-constraint-list">
              {(card.constraints || []).map((row) => (
                <li
                  key={row.id}
                  className="place-constraint-row"
                  data-testid={`place-card-constraint-${row.id}`}
                >
                  <span className="place-constraint-label">{row.label}</span>
                  <span className="place-constraint-state">
                    {row.applies === true
                      ? "Applies"
                      : row.applies === false
                        ? "Does not apply"
                        : row.note || "No data"}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          {/* 9. Holder */}
          <section
            className="place-card-holder"
            aria-label="Holder"
            data-testid="place-card-holder"
          >
            <h3 className="place-card-section">Holder</h3>
            <p className="place-card-holder-label">
              {card.holder?.label || "private, not shown"}
            </p>
            {card.holder?.note ? (
              <p className="place-card-meta">{card.holder.note}</p>
            ) : null}
          </section>

          {/* 10. Sources and licences */}
          <section
            className="place-card-sources"
            aria-label="Sources and licences"
            data-testid="place-card-sources"
          >
            <h3 className="place-card-section">Sources and licences</h3>
            <ul className="place-layer-list" data-testid="place-card-layers">
              {card.layers.map((layer) => (
                <li
                  key={layer.id}
                  className="place-layer-row"
                  data-layer-id={layer.id}
                >
                  <div className="place-layer-top">
                    <span className="place-layer-label">{layer.label}</span>
                    <span className="place-layer-state">
                      {layer.status === "gap"
                        ? "Gap"
                        : layer.status === "linked"
                          ? "Linked"
                          : layer.intersects === true
                            ? "Intersects"
                            : layer.intersects === false
                              ? "No hit"
                              : layer.status}
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
                </li>
              ))}
            </ul>
            {card.data_zone?.status === "ok" && card.data_zone.code ? (
              <p className="place-card-meta">
                <a
                  href={`/place?zone=${encodeURIComponent(card.data_zone.code)}`}
                  data-testid="place-card-hectare-stack-link"
                >
                  Per-hectare ledger stack
                </a>
              </p>
            ) : null}
            {card.links?.length ? (
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
            ) : (
              <p className="place-card-meta">
                <a href="/mission">Mission</a>
                {" · "}
                <a href="/methodology">Methodology</a>
              </p>
            )}
          </section>

          <p
            className="place-card-disclaimer"
            data-testid="place-card-disclaimer"
          >
            {PLACE_CARD_RESEARCH_DISCLAIMER.charAt(0).toUpperCase() +
              PLACE_CARD_RESEARCH_DISCLAIMER.slice(1)}
            .
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

"use client";

import EvidenceTagLegend from "@/components/EvidenceTagLegend";
import {
  PLACE_CARD_CONSTRAINT_LABEL,
  PLACE_CARD_HOLDER_COPY,
  PLACE_CARD_HOW_WE_VALUE_LABEL,
  PLACE_CARD_LIMITS_HEADING,
  PLACE_CARD_SCOTLIS_LABEL,
  dataZoneFieldLabel,
  sanitizePlaceCard,
  valueStatusLabel,
  type PlaceCardPayload,
  type PlaceLayer,
  type PlaceRentTag,
  type PlaceValueStatus,
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
    tag === "market"
      ? "Market"
      : tag === "proxy"
        ? "Modelled"
        : "Estimate (no market price)";
  return (
    <span className={`place-tag tone-${tag}`} data-testid={`place-tag-${tag}`}>
      {label}
    </span>
  );
}

function StatusChip({ status }: { status: PlaceValueStatus }) {
  return (
    <span
      className={`place-value-status tone-${status}`}
      data-testid={`place-value-status-${status}`}
    >
      {valueStatusLabel(status)}
    </span>
  );
}

function layerLicence(layer: PlaceLayer): string {
  return layer.licence?.trim() || "Licence not recorded";
}

/** Gap copy for unknown / missing constraint coverage. */
function LimitsGapLine({ testId }: { testId: string }) {
  return (
    <p className="place-card-meta" data-testid={testId}>
      No data here yet.{" "}
      <a href="/data#gaps">Why?</a>
    </p>
  );
}

/**
 * Designer ledger redesign place card — value / limits IA; DZ2022; no £.
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
  const dz2011Secondary = (zone?.zones ?? []).find((z) => z.vintage === 2011);
  const iz = card?.intermediate_zone;
  // Never show "No data" when the IZ code is known.
  const izName = iz?.name?.trim() || null;
  const izCode = iz?.code ? String(iz.code) : null;
  const izNote = iz?.note?.trim() || null;
  const izPending = Boolean(izCode && !izName);
  // Code known but name/note missing → "name not loaded yet" (never "No data").
  const izDisplay = izName
    ? izName
    : izCode
      ? izNote || "name not loaded yet"
      : izNote || "No data";
  const placeName =
    card?.place_label?.trim() ||
    card?.council_name?.trim() ||
    card?.postcode?.trim() ||
    zone?.name?.trim() ||
    "This place";
  const valueRows = (card?.agr_rows || []).filter((row) => row.applies !== false);
  // Show every constraint row (applies true / false / unknown).
  const limitRows = card?.constraints ?? [];
  const landOutline = card?.land_outline ?? null;
  const outlineStatus = landOutline?.status || card?.land_register_outline?.status;
  const outlineNote =
    landOutline?.note ||
    card?.land_register_outline?.note ||
    null;
  const outlineArea =
    typeof landOutline?.area_sqm === "number" && Number.isFinite(landOutline.area_sqm)
      ? landOutline.area_sqm
      : typeof card?.parcel?.area_sqm === "number" &&
          Number.isFinite(card.parcel.area_sqm)
        ? card.parcel.area_sqm
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
            <div className="place-card-field">
              <dt data-testid="place-card-data-zone-label">
                {dataZoneFieldLabel(zone?.vintage === 2011 ? 2011 : 2022)}
              </dt>
              <dd data-testid="place-card-data-zone">
                {dzCode ? (
                  <>
                    <span className="place-card-dz-code">{dzCode}</span>
                    <span
                      className="place-card-meta-inline"
                      data-testid="place-card-dz-vintage"
                    >
                      {" "}
                      · {zone?.vintage === 2011 ? "2011" : "2022"}
                    </span>
                    {zone?.name ? (
                      <span className="place-card-meta-inline">
                        {" "}
                        · {zone.name}
                      </span>
                    ) : null}
                    {zone?.vintage !== 2011 && dz2011Secondary?.code ? (
                      <span
                        className="place-card-dz-secondary"
                        data-testid="place-card-dz-2011"
                      >
                        Also on 2011 map: {dz2011Secondary.code}
                        {dz2011Secondary.name
                          ? ` · ${dz2011Secondary.name}`
                          : ""}
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

            <div className="place-card-field">
              <dt>Intermediate Zone</dt>
              <dd data-testid="place-card-intermediate-zone">
                {izCode || izName ? (
                  <>
                    <span
                      data-testid="place-card-iz-name"
                      className={izPending ? "place-card-no-data" : undefined}
                    >
                      {izDisplay}
                    </span>
                    {izCode ? (
                      <span className="place-card-meta-inline"> · {izCode}</span>
                    ) : null}
                  </>
                ) : (
                  <span className="place-card-no-data">{izDisplay}</span>
                )}
              </dd>
            </div>

            <div className="place-card-field">
              <dt>Council</dt>
              <dd data-testid="place-card-council">
                {card.council_name || (
                  <span className="place-card-no-data">No data</span>
                )}
              </dd>
            </div>

            <div className="place-card-field">
              <dt>Square reference</dt>
              <dd data-testid="place-card-square-reference">
                {card.square_reference}
              </dd>
            </div>
          </dl>

          {(outlineStatus || outlineArea != null || outlineNote) && (
            <section
              className="place-card-land-outline"
              aria-label="Land outline"
              data-testid="place-card-land-outline"
            >
              <h3 className="place-card-section">Land outline</h3>
              {outlineStatus ? (
                <p className="place-card-meta" data-testid="place-card-outline-status">
                  {outlineStatus === "inside_outline"
                    ? "Inside a registered land outline"
                    : outlineStatus === "no_outline"
                      ? "No registered outline at this point"
                      : outlineStatus}
                </p>
              ) : null}
              {outlineArea != null ? (
                <p className="place-card-meta" data-testid="place-card-outline-area">
                  About {Math.round(outlineArea).toLocaleString("en-GB")} m²
                </p>
              ) : null}
              {outlineNote ? (
                <p className="place-card-meta">{outlineNote}</p>
              ) : null}
            </section>
          )}

          {/* Chip key only while Market / Modelled / Estimate chips are on screen. */}
          {valueRows.length > 0 ? <EvidenceTagLegend compact /> : null}

          <section
            className="place-card-agr"
            aria-label="What gives this land value"
            data-testid="place-card-value"
          >
            <h3 className="place-card-section">What gives this land value</h3>
            <ul className="place-agr-list">
              {valueRows.map((row) => (
                <li
                  key={row.id}
                  className="place-agr-row"
                  data-testid={`place-card-agr-${row.id}`}
                >
                  <div className="place-agr-row-main">
                    <span className="place-agr-label">{row.label}</span>
                    <TagChip tag={row.tag} />
                    <StatusChip status={row.status} />
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
          </section>

          <section
            className="place-card-constraints"
            aria-label={PLACE_CARD_LIMITS_HEADING}
            data-testid="place-card-limits"
          >
            <h3 className="place-card-section">{PLACE_CARD_LIMITS_HEADING}</h3>
            <p
              className="place-card-constraint-banner"
              data-testid="place-card-constraint-banner"
            >
              {PLACE_CARD_CONSTRAINT_LABEL}
            </p>
            {limitRows.length ? (
              <ul className="place-constraint-list">
                {limitRows.map((row) => (
                  <li
                    key={row.id}
                    className="place-constraint-row"
                    data-testid={`place-card-constraint-${row.id}`}
                  >
                    <span className="place-constraint-label">{row.label}</span>
                    <span className="place-constraint-state">
                      {row.applies === true ? (
                        "Applies"
                      ) : row.applies === false ? (
                        "Does not apply"
                      ) : (
                        <>
                          No data here yet.{" "}
                          <a
                            href="/data#gaps"
                            data-testid={`place-card-constraint-gap-${row.id}`}
                          >
                            Why?
                          </a>
                        </>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <LimitsGapLine testId="place-card-limits-gap" />
            )}
          </section>

          <p className="place-card-meta">
            <a
              href="/methodology#glossary"
              data-testid="place-card-how-we-value"
            >
              {PLACE_CARD_HOW_WE_VALUE_LABEL}
            </a>
          </p>

          <section
            className="place-card-holder"
            aria-label="Who holds it"
            data-testid="place-card-holder"
          >
            <h3 className="place-card-section">Who holds it</h3>
            <p className="place-card-holder-label" data-testid="place-card-holder-copy">
              {PLACE_CARD_HOLDER_COPY}
            </p>
            {card.holder?.label && card.holder.status === "public_record" ? (
              <p className="place-card-meta">{card.holder.label}</p>
            ) : null}
            {card.holder?.note ? (
              <p className="place-card-meta">{card.holder.note}</p>
            ) : null}
            <p className="place-card-meta">
              <a
                href={card.scotlis?.public_home || "https://scotlis.ros.gov.uk/"}
                target="_blank"
                rel="noreferrer"
                data-testid="place-card-scotlis"
              >
                {PLACE_CARD_SCOTLIS_LABEL}
              </a>
            </p>
          </section>

          <section
            className="place-card-sources"
            aria-label="Where this comes from"
            data-testid="place-card-sources"
          >
            <h3 className="place-card-section">Where this comes from</h3>
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
                <a href="/about">About</a>
                {" · "}
                <a href="/methodology">{PLACE_CARD_HOW_WE_VALUE_LABEL}</a>
              </p>
            )}
          </section>
        </div>
      ) : null}

      {!isLoading && !error && !card ? (
        <p className="place-card-empty">Click the map to look up a place.</p>
      ) : null}
    </aside>
  );
}

export default PlaceCard;

"use client";

import { useState } from "react";

import {
  PLACE_CARD_AGR_LABEL,
  PLACE_CARD_AGR_SUBTITLE,
  PLACE_CARD_COVERS_HOMES_ONLY,
  PLACE_CARD_EXPERIMENTAL_FOOTER,
  PLACE_CARD_FACT_LINE,
  PLACE_CARD_FULLY_ESTIMATED,
  PLACE_CARD_HOW_WE_WORK_HOMES,
  PLACE_CARD_HOW_WE_WORK_LABEL,
  PLACE_CARD_NEIGHBOURHOOD_NOT_ADDRESS,
  PLACE_CARD_NO_HOMES,
  PLACE_CARD_NO_MATCH,
  PLACE_CARD_OUT_OF_SCOTLAND_LINE,
  PLACE_CARD_PARTS_NOTE,
  PLACE_CARD_PART_NOT_YET,
  PLACE_CARD_PRE_POUND,
  PLACE_CARD_RANK_BAND_ENABLED,
  PLACE_CARD_SHOW_SCOTLAND_LABEL,
  PLACE_CARD_TOO_FEW_HOMES,
  PLACE_CARD_TYPICAL_HOME,
  isPlaceCardSeaMiss,
  placeClassChip,
  placeSalesBasisLine,
  placeUnitKind,
  sanitizePlaceCard,
  type PlaceAgrRow,
  type PlaceCardPayload,
  type PlaceRentTag,
  type PlaceUnitKind,
} from "../lib/placeCard";

export type PlaceCardProps = {
  data: PlaceCardPayload | null;
  isLoading?: boolean;
  error?: string | null;
  onClose?: () => void;
  /** SW-028: sea stub — close card and reset map to Scotland national view. */
  onShowScotland?: () => void;
  /** When true, render as a floating HUD card (map shell). Default: true. */
  floating?: boolean;
  /** Extra class on the aside (e.g. place-card-stub for map HUD selectors). */
  className?: string;
  /** After an address / postcode search — show neighbourhood-not-address line. */
  fromAddressSearch?: boolean;
  /** Dwelling count for the unit rule when the API payload omits it. */
  dwellings?: number | null;
  /** Explicit no-match card state (search found nothing). */
  noMatch?: boolean;
};

/** Suggestion 31 — fold the Sasine / no-outline explanation behind a short control. */
const WHY_NO_OUTLINE_LABEL = "Why no outline?";
const NO_OUTLINE_STATUS_LINE = "No registered outline at this point";

/**
 * Survive PlaceCard body remounts (loading flicker / stub→card swap) so the
 * open/closed choice is not lost mid-toggle under CI timing.
 */
const whyNoOutlineExpandedByNote = new Map<string, boolean>();

function WhyNoOutlineBlock({ note }: { note: string }) {
  const [expanded, setExpanded] = useState(
    () => whyNoOutlineExpandedByNote.get(note) ?? false,
  );

  return (
    <div className="place-card-why-no-outline" data-testid="place-card-why-no-outline">
      <p className="place-card-meta place-card-outline-status-row">
        <span data-testid="place-card-outline-status">{NO_OUTLINE_STATUS_LINE}</span>{" "}
        <button
          type="button"
          className="place-card-why-no-outline-btn"
          data-testid="place-card-why-no-outline-btn"
          aria-expanded={expanded}
          onClick={() => {
            // Write the Map before setState so a remount mid-click still
            // rehydrates the intended open/closed value.
            const next = !(whyNoOutlineExpandedByNote.get(note) ?? expanded);
            whyNoOutlineExpandedByNote.set(note, next);
            setExpanded(next);
          }}
        >
          {WHY_NO_OUTLINE_LABEL}
        </button>
      </p>
      {expanded ? (
        <p
          className="place-card-meta place-card-why-no-outline-detail"
          data-testid="place-card-why-no-outline-detail"
        >
          {note}
        </p>
      ) : null}
    </div>
  );
}

/** Visitor-safe CSS tone — never emit the raw API class string `shadow` in HTML. */
function placeTagTone(tag: PlaceRentTag): "market" | "proxy" | "estimate" {
  switch (tag) {
    case "market":
      return "market";
    case "proxy":
      return "proxy";
    case "shadow":
      return "estimate";
    default: {
      const _exhaustive: never = tag;
      return _exhaustive;
    }
  }
}

function ClassChip({ tag }: { tag: PlaceRentTag }) {
  const tone = placeTagTone(tag);
  const label = placeClassChip(tag);
  return (
    <span
      className={`place-tag tone-${tone}`}
      data-testid={`place-tag-${tone}`}
    >
      {label}
    </span>
  );
}

function figureCopy(unit: PlaceUnitKind): string {
  switch (unit) {
    case "no_homes":
      return PLACE_CARD_NO_HOMES;
    case "too_few_homes":
    case "not_applicable":
      return PLACE_CARD_TOO_FEW_HOMES;
    case "typical_home":
      return PLACE_CARD_PRE_POUND;
    default: {
      const _exhaustive: never = unit;
      return _exhaustive;
    }
  }
}

function PartRow({ row }: { row: PlaceAgrRow }) {
  const classTag = (row.class ?? row.tag) as PlaceRentTag;
  const tone = placeTagTone(classTag);
  return (
    <li
      className="place-agr-row"
      data-testid={`place-card-agr-${row.id}`}
      data-range={row.range ?? PLACE_CARD_PART_NOT_YET}
      data-unit={row.unit ?? ""}
      data-confidence={row.confidence ?? ""}
      data-method={row.method ?? ""}
      data-class={tone}
    >
      <div className="place-agr-row-main">
        <span className="place-agr-label">{row.label}</span>
        <ClassChip tag={classTag} />
      </div>
      {row.gloss ? (
        <p className="place-card-part-gloss" data-testid={`place-card-gloss-${row.id}`}>
          {row.gloss}
        </p>
      ) : null}
      <p
        className="place-card-part-range"
        data-testid={`place-card-range-${row.id}`}
      >
        {row.range ?? PLACE_CARD_PART_NOT_YET}
      </p>
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
  );
}

/**
 * UX-10 place card skeleton — Annual Ground Rent first; FP1 part schema; no pounds.
 */
export function PlaceCard({
  data,
  isLoading = false,
  error = null,
  onClose,
  onShowScotland,
  floating = true,
  className,
  fromAddressSearch = false,
  dwellings = null,
  noMatch = false,
}: PlaceCardProps) {
  const card = data ? sanitizePlaceCard(data) : null;
  const seaMiss = Boolean(
    noMatch === false &&
      card &&
      (card.card_state === "sea" || isPlaceCardSeaMiss(card.data_zone)),
  );
  const isNoMatch = Boolean(noMatch || card?.card_state === "no_match");

  const dwellingCount =
    typeof dwellings === "number" && Number.isFinite(dwellings)
      ? dwellings
      : typeof card?.dwellings === "number" && Number.isFinite(card.dwellings)
        ? card.dwellings
        : null;
  const unit = placeUnitKind(dwellingCount);
  // Explicit API state only — dwellings ≤ 0 uses too_few_homes via placeUnitKind.
  const unitEffective: PlaceUnitKind =
    card?.card_state === "no_homes" ? "no_homes" : unit;
  const fullyEstimated = Boolean(card?.fully_estimated);
  const valueRows = (card?.agr_rows || []).filter((row) => row.applies !== false);
  const salesBasis = placeSalesBasisLine(
    card?.sales_year_from,
    card?.sales_year_to,
    card?.confidence,
  );

  const landOutline = card?.land_outline ?? null;
  const outlineStatus =
    landOutline?.status || card?.land_register_outline?.status;
  const outlineNote =
    landOutline?.note || card?.land_register_outline?.note || null;
  const outlineArea =
    typeof landOutline?.area_sqm === "number" && Number.isFinite(landOutline.area_sqm)
      ? landOutline.area_sqm
      : typeof card?.parcel?.area_sqm === "number" &&
          Number.isFinite(card.parcel.area_sqm)
        ? card.parcel.area_sqm
        : null;

  const placeName =
    card?.place_label?.trim() ||
    card?.data_zone?.name?.trim() ||
    card?.council_name?.trim() ||
    card?.postcode?.trim() ||
    "This place";
  const councilLine = card?.council_name?.trim() || null;

  const shellClass = [
    floating ? "hud-card hud-place place-card" : "place-card place-card-standalone",
    seaMiss ? "place-card-sea-miss" : null,
    isNoMatch && !isLoading ? "place-card-no-match" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const figureText = figureCopy(unitEffective);
  // Rank band stays OFF for UX10-1 (flag constant).
  void PLACE_CARD_RANK_BAND_ENABLED;

  return (
    <aside
      className={shellClass}
      role="dialog"
      aria-label="Place card"
      data-testid="place-card"
      data-unit={unitEffective}
      data-fully-estimated={fullyEstimated ? "true" : "false"}
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
        <div
          className="place-card-loading"
          aria-busy="true"
          data-testid="place-card-loading"
        >
          <p className="place-card-loading-label">Looking up this spot…</p>
          <div
            className="place-card-placeholder-rows"
            data-testid="place-card-placeholders"
            aria-hidden="true"
          >
            <div className="place-card-placeholder-row place-card-placeholder-title" />
            <div className="place-card-placeholder-row place-card-placeholder-meta" />
            <div className="place-card-placeholder-row place-card-placeholder-wide" />
            <div className="place-card-placeholder-row" />
            <div className="place-card-placeholder-row" />
          </div>
        </div>
      ) : null}

      {error && !isNoMatch ? (
        <p className="place-card-error" role="alert" data-testid="place-card-error">
          {error}
        </p>
      ) : null}

      {!isLoading && isNoMatch ? (
        <div className="place-card-body place-card-state" data-testid="place-card-no-match">
          <p className="place-card-meta">{PLACE_CARD_NO_MATCH}</p>
        </div>
      ) : null}

      {!isLoading && !error && card && seaMiss ? (
        <>
          <p
            className="place-card-sea-line"
            data-testid="place-card-out-of-scotland"
          >
            {/* Inner span = line text box for SW-030 (excludes × padding). */}
            <span data-testid="place-card-sea-line-text">
              {PLACE_CARD_OUT_OF_SCOTLAND_LINE}
            </span>
          </p>
          {onShowScotland ? (
            <button
              type="button"
              className="place-card-show-scotland"
              data-testid="place-card-show-scotland"
              onClick={onShowScotland}
            >
              {PLACE_CARD_SHOW_SCOTLAND_LABEL}
            </button>
          ) : null}
        </>
      ) : null}

      {!isLoading && !error && card && !seaMiss && !isNoMatch ? (
        <div className="place-card-body">
          {/* Peek (mobile) / top of panel (desktop): name + figure + disclaimer */}
          <div className="place-card-peek" data-testid="place-card-peek">
            <header className="place-card-header">
              <h2 className="place-card-title" data-testid="place-card-place">
                {placeName}
              </h2>
              {councilLine ? (
                <p className="place-card-council" data-testid="place-card-council">
                  {councilLine}
                </p>
              ) : null}
            </header>

            <p
              className="place-card-figure"
              data-testid="place-card-figure"
            >
              {figureText}
            </p>
            <p
              className="place-card-covers"
              data-testid="place-card-covers-homes"
            >
              {PLACE_CARD_COVERS_HOMES_ONLY}
            </p>
            <p
              className="place-card-experimental-footer place-card-experimental-footer-peek"
              data-testid="place-card-experimental-footer"
            >
              {PLACE_CARD_EXPERIMENTAL_FOOTER}
            </p>
          </div>

          <div className="place-card-sheet-body" data-testid="place-card-sheet-body">
            {unitEffective === "typical_home" ? (
              <>
                <p
                  className="place-card-typical"
                  data-testid="place-card-typical-home"
                >
                  {PLACE_CARD_TYPICAL_HOME}
                </p>
                {fromAddressSearch ? (
                  <p
                    className="place-card-neighbourhood"
                    data-testid="place-card-neighbourhood-not-address"
                  >
                    {PLACE_CARD_NEIGHBOURHOOD_NOT_ADDRESS}
                  </p>
                ) : null}
              </>
            ) : null}

            <section
              className="place-card-agr-heading"
              aria-label={PLACE_CARD_AGR_LABEL}
              data-testid="place-card-agr-heading"
            >
              <h3 className="place-card-section" data-testid="place-card-agr-label">
                {PLACE_CARD_AGR_LABEL}
              </h3>
              <p
                className="place-card-agr-subtitle"
                data-testid="place-card-agr-subtitle"
              >
                {PLACE_CARD_AGR_SUBTITLE}
              </p>
            </section>

            {unitEffective === "typical_home" && !fullyEstimated && salesBasis ? (
              <p
                className="place-card-sales-basis"
                data-testid="place-card-sales-basis"
              >
                {salesBasis}
              </p>
            ) : null}

            {fullyEstimated && unitEffective === "typical_home" ? (
              <p
                className="place-card-fully-estimated-marker"
                data-testid="place-card-fully-estimated"
                data-wider-band="true"
              >
                {PLACE_CARD_FULLY_ESTIMATED}
              </p>
            ) : null}

            <p className="place-card-fact" data-testid="place-card-fact">
              {PLACE_CARD_FACT_LINE}
            </p>

            {/* Surface row always visible (Suggestion 31 first-value-row). */}
            <ul className="place-agr-list place-agr-list-surface">
              {valueRows
                .filter((row) => row.id === "surface")
                .map((row) => (
                  <PartRow key={row.id} row={row} />
                ))}
            </ul>

            <details
              className="place-card-parts"
              data-testid="place-card-parts"
            >
              <summary className="place-card-parts-summary">Parts</summary>
              <ul className="place-agr-list">
                {valueRows
                  .filter((row) => row.id !== "surface")
                  .map((row) => (
                    <PartRow key={row.id} row={row} />
                  ))}
              </ul>
              <p
                className="place-card-parts-note"
                data-testid="place-card-parts-note"
              >
                {PLACE_CARD_PARTS_NOTE}
              </p>
            </details>

            {(outlineStatus || outlineArea != null || outlineNote) && (
              <section
                className="place-card-land-outline"
                aria-label="Land outline"
                data-testid="place-card-land-outline"
              >
                <h3 className="place-card-section">Land outline</h3>
                {outlineStatus === "no_outline" && outlineNote ? (
                  <WhyNoOutlineBlock note={outlineNote} />
                ) : (
                  <>
                    {outlineStatus ? (
                      <p
                        className="place-card-meta"
                        data-testid="place-card-outline-status"
                      >
                        {outlineStatus === "inside_outline"
                          ? "Inside a registered land outline"
                          : outlineStatus === "no_outline"
                            ? NO_OUTLINE_STATUS_LINE
                            : outlineStatus}
                      </p>
                    ) : null}
                    {outlineNote ? (
                      <p className="place-card-meta">{outlineNote}</p>
                    ) : null}
                  </>
                )}
                {outlineArea != null ? (
                  <p className="place-card-meta" data-testid="place-card-outline-area">
                    About {Math.round(outlineArea).toLocaleString("en-GB")} m²
                  </p>
                ) : null}
              </section>
            )}

            <div className="place-card-how" data-testid="place-card-how-we-work">
              <a
                href="/methodology"
                className="place-card-how-link"
                data-testid="place-card-methodology-link"
              >
                {PLACE_CARD_HOW_WE_WORK_LABEL}
              </a>
              <p
                className="place-card-how-homes"
                data-testid="place-card-how-homes-only"
              >
                {PLACE_CARD_HOW_WE_WORK_HOMES}
              </p>
            </div>
          </div>

          <p
            className="place-card-experimental-footer place-card-experimental-footer-sticky"
            data-testid="place-card-experimental-footer-sticky"
            aria-hidden="true"
          >
            {PLACE_CARD_EXPERIMENTAL_FOOTER}
          </p>
        </div>
      ) : null}

      {!isLoading && !error && !card && !isNoMatch ? (
        <p className="place-card-empty">Click the map to look up a place.</p>
      ) : null}
    </aside>
  );
}

export default PlaceCard;

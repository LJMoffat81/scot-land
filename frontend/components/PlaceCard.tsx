"use client";

import { useState } from "react";

import {
  formatGbpCentralWithRange,
  GBP_LIVE_UNDER_REVIEW,
  gbpLiveFromCard,
  type SurfaceRentDisplay,
} from "../lib/gbpLive";
import {
  PLACE_CARD_AGR_LABEL,
  PLACE_CARD_AGR_SUBTITLE,
  PLACE_CARD_COVERS_HOMES_ONLY,
  PLACE_CARD_EXPERIMENTAL_FOOTER,
  PLACE_CARD_FACT_LINE,
  PLACE_CARD_FIGURE_STATUS,
  PLACE_CARD_FIGURE_WHY_HREF,
  PLACE_CARD_FIGURE_WHY_LABEL,
  PLACE_CARD_FULLY_ESTIMATED,
  PLACE_CARD_HOW_WE_WORK_HOMES,
  PLACE_CARD_HOW_WE_WORK_LABEL,
  PLACE_CARD_MAP_REFERENCE_COPY_FAIL,
  PLACE_CARD_MAP_REFERENCE_ENABLED,
  PLACE_CARD_MAP_REFERENCE_LABEL,
  PLACE_CARD_NEIGHBOURHOOD_NOT_ADDRESS,
  PLACE_CARD_NO_HOMES,
  PLACE_CARD_NO_MATCH,
  PLACE_CARD_OUT_OF_SCOTLAND_LINE,
  PLACE_CARD_PARTS_NOTE,
  PLACE_CARD_PARTS_SUMMARY,
  PLACE_CARD_PART_NOT_YET,
  PLACE_CARD_LAND_VALUES_COMING_SOON,
  PLACE_CARD_PRE_POUND,
  PLACE_CARD_RANK_BAND_ENABLED,
  PLACE_CARD_SHOW_SCOTLAND_LABEL,
  PLACE_CARD_TOO_FEW_HOMES,
  PLACE_CARD_TYPICAL_HOME,
  isPlaceCardSeaMiss,
  mapReferenceNumbers,
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

function MapReferenceCopy({ value }: { value: string }) {
  const [done, setDone] = useState(false);
  const [failMsg, setFailMsg] = useState<string | null>(null);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setFailMsg(null);
      setDone(true);
      window.setTimeout(() => setDone(false), 1500);
    } catch {
      setDone(false);
      setFailMsg(PLACE_CARD_MAP_REFERENCE_COPY_FAIL);
    }
  }

  return (
    <>
      <button
        type="button"
        className="place-card-map-reference-copy"
        onClick={() => void onCopy()}
        data-testid="place-card-map-reference-copy"
        aria-label={`Copy ${PLACE_CARD_MAP_REFERENCE_LABEL}`}
      >
        {done ? "Copied" : "Copy"}
      </button>
      {failMsg ? (
        <span
          className="place-card-map-reference-copy-fail"
          data-testid="place-card-map-reference-copy-fail"
          role="status"
        >
          {failMsg}
        </span>
      ) : null}
    </>
  );
}

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

function surfacePartRange(
  row: PlaceAgrRow,
  display: SurfaceRentDisplay | null | undefined,
  gbpLive: boolean,
): string {
  if (!gbpLive || row.id !== "surface") {
    return row.range ?? PLACE_CARD_PART_NOT_YET;
  }
  if (display?.state === "under_review") {
    return display.label?.trim() || GBP_LIVE_UNDER_REVIEW;
  }
  if (
    display?.state === "ok" &&
    display.low != null &&
    display.central != null &&
    display.high != null
  ) {
    return formatGbpCentralWithRange(display.low, display.central, display.high)
      .range;
  }
  // Placeholder / hidden — never show £.
  return row.range ?? PLACE_CARD_PART_NOT_YET;
}

function PartRow({
  row,
  display,
  gbpLive,
  showFigureWhy,
}: {
  row: PlaceAgrRow;
  display?: SurfaceRentDisplay | null;
  gbpLive: boolean;
  /** Idea 17/24 — unpublished figure status + Why? on the first value row. */
  showFigureWhy?: boolean;
}) {
  const classTag = (row.class ?? row.tag) as PlaceRentTag;
  const tone = placeTagTone(classTag);
  const rangeText = surfacePartRange(row, display, gbpLive);
  const liveOk =
    gbpLive &&
    row.id === "surface" &&
    display?.state === "ok" &&
    display.low != null &&
    display.central != null &&
    display.high != null;
  const estimateLabel = liveOk
    ? display.estimate_label || row.estimate_label
    : null;
  const rentRateWording = liveOk
    ? display.rent_rate_wording || row.rent_rate_wording
    : null;
  return (
    <li
      className="place-agr-row"
      data-testid={`place-card-agr-${row.id}`}
      data-range={rangeText}
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
        {rangeText}
      </p>
      {showFigureWhy && !liveOk ? (
        <p
          className="place-card-figure-status"
          data-testid="place-card-figure-status"
        >
          {PLACE_CARD_FIGURE_STATUS}{" "}
          <a
            href={PLACE_CARD_FIGURE_WHY_HREF}
            data-testid="place-card-figure-why"
          >
            {PLACE_CARD_FIGURE_WHY_LABEL}
          </a>
        </p>
      ) : null}
      {estimateLabel ? (
        <p
          className="place-card-estimate-label"
          data-testid={`place-card-estimate-label-${row.id}`}
        >
          {estimateLabel}
        </p>
      ) : null}
      {rentRateWording ? (
        <p
          className="place-card-rent-rate-wording"
          data-testid={`place-card-rent-rate-${row.id}`}
        >
          {rentRateWording}
        </p>
      ) : null}
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
    // UX-05 hug CSS + e2e still key on place-card-search-miss; keep no-match as alias.
    isNoMatch && !isLoading ? "place-card-no-match place-card-search-miss" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const gbpLive = gbpLiveFromCard(card);
  const surfaceDisplay = (card?.surface_rent_display ??
    null) as SurfaceRentDisplay | null;
  let figureText = figureCopy(unitEffective);
  let figureRange: string | null = null;
  let figureEstimate: string | null = null;
  if (gbpLive && unitEffective === "typical_home") {
    if (surfaceDisplay?.state === "under_review") {
      figureText = surfaceDisplay.label?.trim() || GBP_LIVE_UNDER_REVIEW;
    } else if (
      surfaceDisplay?.state === "ok" &&
      surfaceDisplay.low != null &&
      surfaceDisplay.central != null &&
      surfaceDisplay.high != null
    ) {
      const formatted = formatGbpCentralWithRange(
        surfaceDisplay.low,
        surfaceDisplay.central,
        surfaceDisplay.high,
      );
      figureText = formatted.central;
      figureRange = formatted.range;
      figureEstimate = surfaceDisplay.estimate_label ?? null;
    }
    // placeholder / hidden → keep PRE_POUND (no £).
  }
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
          data-testid="place-card-close"
          aria-label="Close place card"
          // Dismiss on pointerdown + stopPropagation so the card unmounts
          // before mouseup; otherwise the same gesture can hit the map and
          // re-open inspect (sea-miss stub stays up — UX10-2 Show legend).
          onPointerDown={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onClose();
          }}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            onClose();
          }}
        >
          ×
        </button>
      ) : null}

      {/* Keep an existing sea-miss line mounted across re-inspect loading so
          SW-030 × padding stays measurable (no spinner flash / remount). */}
      {isLoading && !seaMiss ? (
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
          <p className="place-card-meta place-card-no-match-line">
            <span data-testid="place-card-no-match-text">
              {PLACE_CARD_NO_MATCH}
            </span>
          </p>
        </div>
      ) : null}

      {/* Keep sea-line mounted across re-inspect/loading flicker (SW-030 / UX-01 e2e). */}
      {!error && card && seaMiss ? (
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
              {PLACE_CARD_MAP_REFERENCE_ENABLED && card.square_reference ? (
                <p
                  className="place-card-map-reference"
                  data-testid="place-card-map-reference"
                >
                  <span className="place-card-map-reference-label">
                    {PLACE_CARD_MAP_REFERENCE_LABEL}
                  </span>{" "}
                  <span data-testid="place-card-square-reference">
                    {mapReferenceNumbers(card.square_reference)}
                  </span>{" "}
                  <MapReferenceCopy
                    value={mapReferenceNumbers(card.square_reference)}
                  />
                </p>
              ) : null}
            </header>

            <p
              className="place-card-figure"
              data-testid="place-card-figure"
            >
              {figureText}
              {figureRange ? (
                <span
                  className="place-card-figure-range"
                  data-testid="place-card-figure-range"
                >
                  {" "}
                  ({figureRange})
                </span>
              ) : null}
            </p>
            {figureText === PLACE_CARD_PRE_POUND ? (
              <p
                className="place-card-land-values-coming-soon"
                data-testid="place-card-land-values-coming-soon"
              >
                {PLACE_CARD_LAND_VALUES_COMING_SOON}
              </p>
            ) : null}
            {figureEstimate ? (
              <p
                className="place-card-figure-estimate"
                data-testid="place-card-figure-estimate"
              >
                {figureEstimate}
              </p>
            ) : null}
            {gbpLive && surfaceDisplay?.state === "under_review" ? (
              <p
                className="place-card-under-review"
                data-testid="place-card-under-review"
              >
                {surfaceDisplay.label?.trim() || GBP_LIVE_UNDER_REVIEW}
              </p>
            ) : null}
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

          {/* SW-047: value rows stay outside the scrollable sheet so height is kept. */}
          <div
            className="place-card-value-block"
            data-testid="place-card-value-block"
          >
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
            <ul
              className="place-agr-list place-agr-list-surface"
              data-testid="place-card-value-rows"
            >
              {valueRows
                .filter((row) => row.id === "surface")
                .map((row) => (
                  <PartRow
                    key={row.id}
                    row={row}
                    display={surfaceDisplay}
                    gbpLive={gbpLive}
                    showFigureWhy
                  />
                ))}
            </ul>
          </div>

          <div className="place-card-sheet-body" data-testid="place-card-sheet-body">
            <details
              className="place-card-parts"
              data-testid="place-card-parts"
            >
              <summary className="place-card-parts-summary">
                {PLACE_CARD_PARTS_SUMMARY}
              </summary>
              <ul className="place-agr-list">
                {valueRows
                  .filter((row) => row.id !== "surface")
                  .map((row) => (
                    <PartRow
                      key={row.id}
                      row={row}
                      display={null}
                      gbpLive={false}
                    />
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

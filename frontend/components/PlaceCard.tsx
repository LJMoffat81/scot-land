"use client";

import {
  GBP_LIVE_ESTIMATE_UNAVAILABLE,
  GBP_LIVE_UNIT_WORDING,
  gbpLiveFromCard,
  type SurfaceRentDisplay,
} from "../lib/gbpLive";
import {
  PLACE_CARD_AGR_LABEL,
  PLACE_CARD_AGR_SCOPE_NOTE,
  PLACE_CARD_AGR_SUBTITLE,
  PLACE_CARD_ERROR_LINE,
  PLACE_CARD_EXPERIMENTAL_FOOTER,
  PLACE_CARD_FACT_LINE,
  PLACE_CARD_FIGURE_STATUS,
  PLACE_CARD_FOLD_NOT_YET,
  PLACE_CARD_HOW_WE_WORK_HOMES,
  PLACE_CARD_HOW_WE_WORK_LABEL,
  PLACE_CARD_LOADING_LABEL,
  PLACE_CARD_OUT_OF_SCOTLAND_LINE,
  PLACE_CARD_OUTSIDE_SCOTLAND_TITLE,
  PLACE_CARD_PARTS_SUMMARY,
  PLACE_CARD_PRE_POUND,
  PLACE_CARD_RANK_BAND_ENABLED,
  PLACE_CARD_SEA_TITLE,
  PLACE_CARD_SEE_ROADMAP_HREF,
  PLACE_CARD_SEE_ROADMAP_LABEL,
  PLACE_CARD_SHOW_SCOTLAND_LABEL,
  PLACE_CARD_TOO_FEW_HOMES,
  PLACE_CARD_TRY_AGAIN_LABEL,
  PLACE_CARD_TYPICAL_HOME,
  formatPlaceCardGbpRange,
  isPlaceCardSeaMiss,
  placeClassChip,
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
  /** Error state — retry the last lookup. */
  onRetry?: () => void;
  /** When true, render as a floating HUD card (map shell). Default: true. */
  floating?: boolean;
  /** Extra class on the aside (e.g. place-card-stub for map HUD selectors). */
  className?: string;
  /** @deprecated MAP-CARDS §6 — neighbourhood-not-address line removed. */
  fromAddressSearch?: boolean;
  /** Dwelling count for the unit rule when the API payload omits it. */
  dwellings?: number | null;
  /** Explicit no-match card state (search found nothing) — parent shows under search. */
  noMatch?: boolean;
  /**
   * GRID-BASE-1 row-6 — e.g. "Grid square NT 25890 73452 (a map grid, not a property)".
   * Empty / omitted keeps the Addendum A4 slot hidden.
   */
  gridSquareLine?: string | null;
};

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

function surfaceLiveRange(
  display: SurfaceRentDisplay | null | undefined,
  gbpLive: boolean,
): string | null {
  if (!gbpLive || !display) return null;
  if (display.state === "under_review") return null;
  if (
    display.state === "ok" &&
    display.low != null &&
    display.central != null &&
    display.high != null
  ) {
    const range = formatPlaceCardGbpRange(display.low, display.central, display.high);
    // Fail-closed: invalid rates surface as unavailable, not a £ string.
    if (range === GBP_LIVE_ESTIMATE_UNAVAILABLE) {
      return GBP_LIVE_ESTIMATE_UNAVAILABLE;
    }
    return range;
  }
  return null;
}

function FoldPartRow({
  row,
  liveRange,
}: {
  row: PlaceAgrRow;
  liveRange: string | null;
}) {
  const classTag = (row.class ?? row.tag) as PlaceRentTag;
  const tone = placeTagTone(classTag);
  const showLive = Boolean(liveRange && row.id === "surface");
  return (
    <li
      className="place-agr-row"
      data-testid={`place-card-agr-${row.id}`}
      data-range={showLive && liveRange ? liveRange : PLACE_CARD_FOLD_NOT_YET}
      data-unit={row.unit ?? ""}
      data-confidence={row.confidence ?? ""}
      data-method={row.method ?? ""}
      data-class={tone}
    >
      <div className="place-agr-row-main">
        <span className="place-agr-label">{row.label}</span>
        {showLive ? <ClassChip tag={classTag} /> : null}
      </div>
      {row.id === "surface" && row.gloss ? (
        <p
          className="place-card-part-gloss"
          data-testid={`place-card-gloss-${row.id}`}
        >
          {row.gloss}
        </p>
      ) : null}
      <p
        className="place-card-part-range"
        data-testid={`place-card-range-${row.id}`}
      >
        {showLive && liveRange ? liveRange : PLACE_CARD_FOLD_NOT_YET}
      </p>
    </li>
  );
}

/**
 * MAP-CARDS §5 place card — answer-first Annual Ground Rent; no map reference;
 * no land outline; status pill once; fold for parts.
 */
export function PlaceCard({
  data,
  isLoading = false,
  error = null,
  onClose,
  onShowScotland,
  onRetry,
  floating = true,
  className,
  dwellings = null,
  noMatch = false,
  gridSquareLine = null,
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
  const unitEffective: PlaceUnitKind =
    card?.card_state === "no_homes" ? "no_homes" : unit;
  const tooFew =
    unitEffective === "too_few_homes" ||
    unitEffective === "not_applicable" ||
    unitEffective === "no_homes";
  const valueRows = (card?.agr_rows || []).filter(
    (row) => row.applies !== false,
  );

  // Title: Intermediate Zone when present — never council as h2 when IZ exists.
  const izName = card?.intermediate_zone?.name?.trim() || null;
  const placeName =
    izName ||
    card?.place_label?.trim() ||
    card?.data_zone?.name?.trim() ||
    (!izName ? card?.council_name?.trim() : null) ||
    card?.postcode?.trim() ||
    "This place";
  const councilLine = card?.council_name?.trim() || null;

  const titleId = "place-card-title";

  const shellClass = [
    floating ? "hud-card hud-place place-card" : "place-card place-card-standalone",
    seaMiss ? "place-card-sea-miss" : null,
    isNoMatch && !isLoading ? "place-card-no-match place-card-search-miss" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const gbpLive = gbpLiveFromCard(card);
  const surfaceDisplay = (card?.surface_rent_display ??
    null) as SurfaceRentDisplay | null;
  const liveAnswerRange =
    !tooFew && unitEffective === "typical_home"
      ? surfaceLiveRange(surfaceDisplay, gbpLive)
      : null;
  const liveRangeOk =
    Boolean(liveAnswerRange) &&
    liveAnswerRange !== GBP_LIVE_ESTIMATE_UNAVAILABLE;
  const liveUnavailable =
    gbpLive &&
    !tooFew &&
    unitEffective === "typical_home" &&
    (surfaceDisplay?.state === "under_review" ||
      liveAnswerRange === GBP_LIVE_ESTIMATE_UNAVAILABLE);
  const surfaceRow = valueRows.find((row) => row.id === "surface");
  const answerChipTag = (surfaceRow?.class ??
    surfaceRow?.tag ??
    "proxy") as PlaceRentTag;

  // Rank band stays OFF for UX10-1 (flag constant).
  void PLACE_CARD_RANK_BAND_ENABLED;

  const seaTitle =
    card?.place_label?.trim() === PLACE_CARD_OUTSIDE_SCOTLAND_TITLE
      ? PLACE_CARD_OUTSIDE_SCOTLAND_TITLE
      : PLACE_CARD_SEA_TITLE;

  // No-match: parent shows under search — no card.
  if (!isLoading && isNoMatch) {
    return null;
  }

  const showTitleForAria =
    Boolean(error && !isLoading) ||
    Boolean(!error && card && seaMiss) ||
    Boolean(!isLoading && !error && card && !seaMiss);

  return (
    <aside
      className={shellClass}
      role="region"
      aria-labelledby={showTitleForAria ? titleId : undefined}
      aria-label={showTitleForAria ? undefined : "Place card"}
      data-testid="place-card"
      data-unit={unitEffective}
      data-fully-estimated={card?.fully_estimated ? "true" : "false"}
      data-zone-code={card?.data_zone?.code?.trim() || undefined}
      data-zone-name={card?.data_zone?.name?.trim() || undefined}
    >
      {onClose ? (
        <button
          type="button"
          className="hud-close"
          onClick={onClose}
          aria-label="Close place card"
          data-testid="place-card-close"
        >
          ×
        </button>
      ) : null}

      {isLoading && !seaMiss ? (
        <div
          className="place-card-loading"
          aria-busy="true"
          data-testid="place-card-loading"
        >
          <p className="place-card-loading-label">{PLACE_CARD_LOADING_LABEL}</p>
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

      {error && !isLoading ? (
        <div
          className="place-card-body place-card-state"
          data-testid="place-card-error"
          role="alert"
        >
          {card && !seaMiss ? (
            <h2
              className="place-card-title"
              id={titleId}
              data-testid="place-card-place"
            >
              {placeName}
            </h2>
          ) : (
            <h2 className="place-card-title" id={titleId} hidden>
              Place
            </h2>
          )}
          <p className="place-card-error-line">{PLACE_CARD_ERROR_LINE}</p>
          <button
            type="button"
            className="place-card-try-again"
            data-testid="place-card-try-again"
            onClick={() => {
              if (onRetry) onRetry();
              else if (onClose) onClose();
            }}
          >
            {PLACE_CARD_TRY_AGAIN_LABEL}
          </button>
        </div>
      ) : null}

      {!error && card && seaMiss ? (
        <>
          <h2
            className="place-card-title"
            id={titleId}
            data-testid="place-card-place"
          >
            {seaTitle}
          </h2>
          <p
            className="place-card-sea-line"
            data-testid="place-card-out-of-scotland"
          >
            <span data-testid="place-card-sea-line-text">
              {PLACE_CARD_OUT_OF_SCOTLAND_LINE}
            </span>
          </p>
          <div className="place-card-sea-actions">
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
            <a
              className="place-card-see-roadmap"
              data-testid="place-card-see-roadmap"
              href={PLACE_CARD_SEE_ROADMAP_HREF}
            >
              {PLACE_CARD_SEE_ROADMAP_LABEL}
            </a>
          </div>
        </>
      ) : null}

      {!isLoading && !error && card && !seaMiss && !isNoMatch ? (
        <div className="place-card-body">
          <header
            className="place-card-header"
            data-testid="place-card-header"
          >
            {/* 1 Title */}
            <h2
              className="place-card-title"
              id={titleId}
              data-testid="place-card-place"
            >
              {placeName}
            </h2>
            {/* 2 Council */}
            {councilLine ? (
              <p className="place-card-council" data-testid="place-card-council">
                {councilLine}
              </p>
            ) : null}
            {/* 3 Scope (rows 1–5 for too-few too) */}
            <p
              className="place-card-typical"
              data-testid="place-card-typical-home"
            >
              {PLACE_CARD_TYPICAL_HOME}
            </p>
            {/* 4 Label + 5 Subtitle */}
            <section
              className="place-card-agr-heading"
              aria-label={`${PLACE_CARD_AGR_LABEL}. ${PLACE_CARD_AGR_SUBTITLE}. ${PLACE_CARD_AGR_SCOPE_NOTE}`}
              data-testid="place-card-agr-heading"
            >
              <h3
                className="place-card-section place-card-agr-label"
                data-testid="place-card-agr-label"
              >
                {PLACE_CARD_AGR_LABEL}
              </h3>
              <p
                className="place-card-agr-subtitle"
                data-testid="place-card-agr-subtitle"
                aria-label={PLACE_CARD_AGR_SUBTITLE}
              >
                {PLACE_CARD_AGR_SUBTITLE}
              </p>
              <p
                className="place-card-agr-scope"
                data-testid="place-card-agr-scope"
                aria-label={PLACE_CARD_AGR_SCOPE_NOTE}
              >
                {PLACE_CARD_AGR_SCOPE_NOTE}
              </p>
            </section>
            {/* 6 Answer (+ addendum A4 hidden slot) */}
            <div
              className="place-card-answer"
              data-testid="place-card-figure"
            >
              {tooFew ? (
                <p
                  className="place-card-too-few"
                  data-testid="place-card-too-few"
                >
                  {PLACE_CARD_TOO_FEW_HOMES}
                </p>
              ) : liveRangeOk ? (
                <>
                  <p className="place-card-figure-range-line">
                    <span data-testid="place-card-figure-range">
                      {liveAnswerRange}
                    </span>{" "}
                    <ClassChip tag={answerChipTag} />
                  </p>
                  <p
                    className="place-card-figure-unit"
                    data-testid="place-card-figure-unit"
                  >
                    {GBP_LIVE_UNIT_WORDING}
                  </p>
                </>
              ) : liveUnavailable ? (
                <p
                  className="place-card-under-review"
                  data-testid="place-card-under-review"
                >
                  {surfaceDisplay?.label?.trim() ||
                    GBP_LIVE_ESTIMATE_UNAVAILABLE}
                </p>
              ) : (
                <>
                  <span
                    className="place-card-status-pill"
                    data-testid="place-card-figure-status"
                  >
                    {PLACE_CARD_FIGURE_STATUS}
                  </span>
                  <p className="place-card-pre-pound">{PLACE_CARD_PRE_POUND}</p>
                </>
              )}
            </div>
            {/* Addendum A4 / GRID-BASE-1 row-6 */}
            {gridSquareLine ? (
              <p
                className="place-card-row6"
                data-testid="place-card-row6-slot"
              >
                {gridSquareLine}
              </p>
            ) : (
              <div
                data-testid="place-card-row6-slot"
                hidden
                aria-hidden="true"
              />
            )}
          </header>

          {/* 7 Why */}
          <p className="place-card-fact" data-testid="place-card-fact">
            {PLACE_CARD_FACT_LINE}
          </p>

          {/* 8 Fold */}
          <details
            className="place-card-parts"
            data-testid="place-card-parts"
          >
            <summary className="place-card-parts-summary">
              {PLACE_CARD_PARTS_SUMMARY}
            </summary>
            <ul
              className="place-agr-list"
              data-testid="place-card-value-rows"
            >
              {valueRows.map((row) => (
                <FoldPartRow
                  key={row.id}
                  row={row}
                  liveRange={
                    row.id === "surface" && liveRangeOk ? liveAnswerRange : null
                  }
                />
              ))}
            </ul>
            <p
              className="place-card-how-homes"
              data-testid="place-card-how-homes-only"
            >
              {PLACE_CARD_HOW_WE_WORK_HOMES}
            </p>
            <div className="place-card-how" data-testid="place-card-how-we-work">
              <a
                href="/methodology"
                className="place-card-how-link"
                data-testid="place-card-methodology-link"
              >
                {PLACE_CARD_HOW_WE_WORK_LABEL}
              </a>
            </div>
          </details>

          <p
            className="place-card-experimental-footer"
            data-testid="place-card-footer"
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

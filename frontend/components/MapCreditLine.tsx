"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import {
  buildMapAttributionPieces,
  OPENFREEMAP_ATTRIBUTION,
  shortLayerSourceName,
} from "@/lib/mapAttributionLine";

export const MAP_CREDIT_SIMPLE =
  "© OpenFreeMap © OpenStreetMap · Sources (1)";

export const MAP_CREDIT_SOURCES_HREF = "/data#licences";

/** Accessible name for the ⓘ control (Wording & UX). */
export const MAP_CREDIT_INFO_LABEL = "Map credits";

/**
 * Visible "Sources (n)" label. Falls back to plain "Sources" when n is not a
 * positive integer (CARD-CLARITY-31OCT-1A).
 */
export function mapCreditSourcesText(n: number): string {
  if (!Number.isInteger(n) || n < 1) return "Sources";
  return `Sources (${n})`;
}

export type MapCreditLineProps = {
  /** Distinct Esri source attributions joined with "; ", or null on Simple. */
  esriAttribution: string | null;
  /** Active layer toggle ids (same set as main's attribution line). */
  activeLayerIds?: readonly string[];
  /** ARCH-5a — tileset id → attribution from the tile manifest. */
  tileCredits?: Readonly<Record<string, string>>;
};

/**
 * One map credit line (MAP-FOOTER-1 / O1 / FRONTEND-BATCH-2 r6 /
 * CARD-CLARITY-31OCT-1A).
 *
 * Visible order: Esri (Aerial) → © OpenFreeMap © OpenStreetMap · Sources (N).
 * Short layer names live in the ⓘ sheet only. `map-attribution-line` always
 * holds the full `buildMapAttributionPieces` join (R1).
 */
export default function MapCreditLine({
  esriAttribution,
  activeLayerIds = [],
  tileCredits,
}: MapCreditLineProps) {
  const [narrow, setNarrow] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const sheetId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 900px)");
    const sync = () => setNarrow(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (!sheetOpen) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setSheetOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sheetOpen]);

  useEffect(() => {
    if (sheetOpen) return;
    if (document.activeElement === document.body) {
      buttonRef.current?.focus();
    }
  }, [sheetOpen]);

  const closeSheet = useCallback(() => {
    setSheetOpen(false);
    queueMicrotask(() => buttonRef.current?.focus());
  }, []);

  const onSheetKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeSheet();
    }
  };

  const pieces = buildMapAttributionPieces(activeLayerIds, tileCredits);
  const piecesJoin = pieces.map((p) => p.text).join(" · ");
  const layerPieces = pieces.filter((p) => p.id !== "basemap");
  const shortNames = layerPieces
    .map((p) => shortLayerSourceName(p))
    .filter((s): s is string => Boolean(s));
  const layerLongJoin = layerPieces.map((p) => p.text).join(" · ");
  const sourceCount = pieces.length + (esriAttribution ? 1 : 0);
  const sourcesLabel = mapCreditSourcesText(sourceCount);

  const sourcesLink = (
    <a href={MAP_CREDIT_SOURCES_HREF} data-testid="map-all-sources">
      {sourcesLabel}
    </a>
  );

  const shortNamesSpan =
    shortNames.length > 0 ? (
      <span
        className="map-credit-short-names"
        data-testid="map-credit-short-names"
      >
        {shortNames.join(" · ")}
        {" · "}
      </span>
    ) : null;

  /**
   * Full pieces join for R1. Long layer licence strings are hidden on the
   * bar at all widths so innerText shows only OSM + Sources (N) (no short
   * names, no long repeat) while textContent and the ⓘ sheet hold the full
   * legal text. Short names are sheet-only (CARD-CLARITY-31OCT-1A).
   */
  const attributionSpan = (
    <span className="map-attribution-line" data-testid="map-attribution-line">
      {OPENFREEMAP_ATTRIBUTION}
      {layerLongJoin ? (
        <span className="map-credit-long-pieces" hidden>
          {" · "}
          {layerLongJoin}
        </span>
      ) : null}
    </span>
  );

  const esriFullPrefix = esriAttribution ? (
    <>
      Powered by{" "}
      <a href="https://www.esri.com" rel="noopener noreferrer">
        Esri
      </a>
      {" | "}
      {esriAttribution}
      {" · "}
    </>
  ) : null;

  const esriNarrowPrefix = esriAttribution ? (
    <>
      Powered by{" "}
      <a href="https://www.esri.com" rel="noopener noreferrer">
        Esri
      </a>
      {" · "}
    </>
  ) : null;

  const sheetBody = (
    <span className="map-credit-sheet-text">
      {esriFullPrefix}
      {shortNamesSpan}
      {piecesJoin}
      {" · "}
      <a href={MAP_CREDIT_SOURCES_HREF}>{sourcesLabel}</a>
    </span>
  );

  const infoButton = (
    <button
      ref={buttonRef}
      type="button"
      className="map-credit-info-btn"
      aria-label={MAP_CREDIT_INFO_LABEL}
      aria-expanded={sheetOpen}
      aria-controls={sheetId}
      data-testid="map-credit-info"
      onClick={() => setSheetOpen(true)}
    >
      <span aria-hidden="true">ⓘ</span>
    </button>
  );

  const sheet = sheetOpen ? (
    <div
      id={sheetId}
      className="map-credit-sheet"
      role="dialog"
      aria-modal="true"
      aria-label={MAP_CREDIT_INFO_LABEL}
      data-testid="map-credit-sheet"
      onKeyDown={onSheetKeyDown}
    >
      <button
        ref={closeRef}
        type="button"
        className="map-credit-sheet-close"
        aria-label="Close map credits"
        data-testid="map-credit-sheet-close"
        onClick={closeSheet}
      >
        ×
      </button>
      <div className="map-credit-sheet-body">{sheetBody}</div>
    </div>
  ) : null;

  if (narrow) {
    return (
      <div
        className="map-credit-line map-credit-line--narrow"
        data-testid="map-credit-line"
      >
        <span className="map-credit-line-text" data-testid="map-credit-line-text">
          {esriNarrowPrefix}
          {attributionSpan}
          {" · "}
          {sourcesLink}
        </span>
        {infoButton}
        {sheet}
      </div>
    );
  }

  return (
    <div className="map-credit-line" data-testid="map-credit-line">
      <span className="map-credit-line-text" data-testid="map-credit-line-text">
        {esriFullPrefix}
        {attributionSpan}
        {" · "}
        {sourcesLink}
      </span>
      {infoButton}
      {sheet}
    </div>
  );
}

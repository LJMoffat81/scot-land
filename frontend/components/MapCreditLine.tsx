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
  "© OpenFreeMap © OpenStreetMap · Sources";

export const MAP_CREDIT_SOURCES_HREF = "/data#licences";

/** Accessible name for the ⓘ control (Wording & UX). */
export const MAP_CREDIT_INFO_LABEL = "Map credits";

export type MapCreditLineProps = {
  /** Distinct Esri source attributions joined with "; ", or null on Simple. */
  esriAttribution: string | null;
  /** Active layer toggle ids (same set as main's attribution line). */
  activeLayerIds?: readonly string[];
  /** ARCH-5a — tileset id → attribution from the tile manifest. */
  tileCredits?: Readonly<Record<string, string>>;
};

/**
 * One map credit line (MAP-FOOTER-1 / O1 / FRONTEND-BATCH-2 r6).
 *
 * Visible order: Esri (Aerial) → short layer names → © OpenFreeMap © OpenStreetMap · Sources.
 * `map-attribution-line` always holds the full `buildMapAttributionPieces` join (R1).
 * On ≤900px, long layer licence strings use display:none so they do not repeat on the
 * visible line (they remain in the ⓘ sheet and in textContent for R1).
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

  const sourcesLink = (
    <a href={MAP_CREDIT_SOURCES_HREF} data-testid="map-all-sources">
      Sources
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
   * Full pieces join for R1. On narrow, long layer strings are display:none so
   * innerText omits them (no repeat) while textContent still matches piecesJoin.
   */
  const attributionSpan = narrow ? (
    <span className="map-attribution-line" data-testid="map-attribution-line">
      {OPENFREEMAP_ATTRIBUTION}
      {layerLongJoin ? (
        <span className="map-credit-long-pieces" hidden>
          {" · "}
          {layerLongJoin}
        </span>
      ) : null}
    </span>
  ) : (
    <span className="map-attribution-line" data-testid="map-attribution-line">
      {piecesJoin}
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
      {piecesJoin}
      {" · "}
      <a href={MAP_CREDIT_SOURCES_HREF}>Sources</a>
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
          {shortNamesSpan}
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
        {shortNamesSpan}
        {attributionSpan}
        {" · "}
        {sourcesLink}
      </span>
    </div>
  );
}

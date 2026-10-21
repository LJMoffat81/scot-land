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
};

/**
 * One map credit line (MAP-FOOTER-1 / O1 / FRONTEND-BATCH-2 r6).
 *
 * Structure (§1):
 * 1. Aerial: `Powered by Esri | {A} · ` (on ≤900px, `{A}` moves into the ⓘ sheet)
 * 2. `map-attribution-line` = `buildMapAttributionPieces(ids)` joined with ` · `
 * 3. ` · Sources` (`map-all-sources`)
 *
 * Narrow: line stays visible (never ⓘ-only). Short layer source names stay on the
 * line; long Esri provider list goes in the sheet. ⓘ accessible name is "Map credits".
 */
export default function MapCreditLine({
  esriAttribution,
  activeLayerIds = [],
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

  const pieces = buildMapAttributionPieces(activeLayerIds);
  const piecesJoin = pieces.map((p) => p.text).join(" · ");
  const layerPieces = pieces.filter((p) => p.id !== "basemap");
  const shortNames = layerPieces
    .map((p) => shortLayerSourceName(p))
    .filter((s): s is string => Boolean(s));

  const sourcesLink = (
    <a href={MAP_CREDIT_SOURCES_HREF} data-testid="map-all-sources">
      Sources
    </a>
  );

  const attributionSpan = (
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

  /** Sheet copy — no duplicate testids. */
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
          {shortNames.length > 0 ? (
            <span
              className="map-credit-short-names"
              data-testid="map-credit-short-names"
            >
              {shortNames.join(" · ")}
              {" · "}
            </span>
          ) : null}
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
    </div>
  );
}

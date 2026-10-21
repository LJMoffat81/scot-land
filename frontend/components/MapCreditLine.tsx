"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

export const MAP_CREDIT_SIMPLE =
  "© OpenFreeMap © OpenStreetMap · Sources";

export const MAP_CREDIT_SOURCES_HREF = "/data#licences";

export type MapCreditLineProps = {
  /** Distinct Esri source attributions joined with "; ", or null on Simple. */
  esriAttribution: string | null;
};

/**
 * One map credit line (MAP-FOOTER-1 / O1). Desktop: full line. ≤900px: ⓘ sheet.
 */
export default function MapCreditLine({ esriAttribution }: MapCreditLineProps) {
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
    // Return focus to the ⓘ control after close.
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

  const line = (
    <span className="map-credit-line-text" data-testid="map-credit-line-text">
      {esriAttribution ? (
        <>
          Powered by{" "}
          <a href="https://www.esri.com" rel="noopener noreferrer">
            Esri
          </a>
          {" | "}
          {esriAttribution}
          {" · "}
        </>
      ) : null}
      © OpenFreeMap © OpenStreetMap ·{" "}
      <a href={MAP_CREDIT_SOURCES_HREF} data-testid="map-credit-sources">
        Sources
      </a>
    </span>
  );

  if (narrow) {
    return (
      <div className="map-credit-line map-credit-line--narrow" data-testid="map-credit-line">
        <button
          ref={buttonRef}
          type="button"
          className="map-credit-info-btn"
          aria-label="Map credits and sources"
          aria-expanded={sheetOpen}
          aria-controls={sheetId}
          data-testid="map-credit-info"
          onClick={() => setSheetOpen(true)}
        >
          <span aria-hidden="true">ⓘ</span>
        </button>
        {sheetOpen ? (
          <div
            id={sheetId}
            className="map-credit-sheet"
            role="dialog"
            aria-modal="true"
            aria-label="Map credits and sources"
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
            <div className="map-credit-sheet-body">{line}</div>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="map-credit-line" data-testid="map-credit-line">
      {line}
    </div>
  );
}

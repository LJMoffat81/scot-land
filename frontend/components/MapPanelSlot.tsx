"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  type ReactNode,
} from "react";

export type PanelSlotKind = "closed" | "place" | "layers";
export type PanelDetent = "peek" | "half" | "full";

export type MapPanelSlotProps = {
  kind: PanelSlotKind;
  /** Mobile bottom-sheet detent (ignored on desktop layout via CSS). */
  detent: PanelDetent;
  onDetentChange: (next: PanelDetent) => void;
  /** Desktop: slot collapsed to 48px edge tab. */
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  /** Close / clear selection (second ×, Esc after collapse, Back). */
  onClose: () => void;
  /** Collapse desktop slot (first ×) or step down mobile detent. */
  onRequestDismiss: () => void;
  /** Place name for the collapse tab (e.g. "‹ Old Town"). */
  placeName?: string | null;
  /** Announce string for the polite live region. */
  liveMessage?: string;
  /** Mobile Layers at full → dialog; place is always region (child). */
  layersModal?: boolean;
  /** Map stage element to mark inert when layers modal. */
  mapInert?: boolean;
  /** Override when a second slot is open (place stays `map-panel-slot`). */
  slotTestId?: string;
  /** Place card supplies its own close; the sheet × is the empty desktop strip. */
  showSlotClose?: boolean;
  children: ReactNode;
  className?: string;
};

const DETENT_ORDER: PanelDetent[] = ["peek", "half", "full"];

function detentLabel(d: PanelDetent): string {
  switch (d) {
    case "peek":
      return "Panel peek height";
    case "half":
      return "Panel half height";
    case "full":
      return "Panel full height";
    default: {
      const _exhaustive: never = d;
      return _exhaustive;
    }
  }
}

/**
 * Single panel slot — desktop left column / mobile bottom sheet.
 * Place XOR Layers; parent owns which child is rendered.
 */
export default function MapPanelSlot({
  kind,
  detent,
  onDetentChange,
  collapsed,
  onCollapsedChange,
  onClose,
  onRequestDismiss,
  placeName,
  liveMessage,
  layersModal = false,
  slotTestId = "map-panel-slot",
  showSlotClose = true,
  children,
  className,
}: MapPanelSlotProps) {
  const headingId = useId();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const open = kind !== "closed";

  const cycleDetentUp = useCallback(() => {
    const idx = DETENT_ORDER.indexOf(detent);
    const next = DETENT_ORDER[Math.min(idx + 1, DETENT_ORDER.length - 1)]!;
    onDetentChange(next);
  }, [detent, onDetentChange]);

  const cycleDetentDown = useCallback(() => {
    const idx = DETENT_ORDER.indexOf(detent);
    if (idx <= 0) {
      onRequestDismiss();
      return;
    }
    onDetentChange(DETENT_ORDER[idx - 1]!);
  }, [detent, onDetentChange, onRequestDismiss]);

  const onHandleActivate = useCallback(() => {
    if (detent === "full") cycleDetentDown();
    else cycleDetentUp();
  }, [cycleDetentDown, cycleDetentUp, detent]);

  useEffect(() => {
    if (!open || collapsed) return;
    const el = document.getElementById(headingId);
    el?.focus?.();
  }, [open, kind, collapsed, headingId]);

  if (!open) {
    return (
      <div
        className="map-live-region-host"
        aria-live="polite"
        aria-atomic="true"
        data-testid="map-live-region"
      >
        {liveMessage || ""}
      </div>
    );
  }

  if (collapsed && kind === "place") {
    return (
      <>
        <div
          className="map-live-region-host"
          aria-live="polite"
          aria-atomic="true"
          data-testid="map-live-region"
        >
          {liveMessage || "Panel collapsed"}
        </div>
        <div className="map-panel-collapse-tab-wrap">
          <button
            type="button"
            className="map-panel-collapse-tab"
            data-testid="panel-collapse-tab"
            aria-label={
              placeName
                ? `Reopen place card for ${placeName}`
                : "Reopen place card"
            }
            onClick={() => onCollapsedChange(false)}
          >
            ‹ {placeName?.trim() || "Place"}
          </button>
          <button
            type="button"
            className="map-panel-collapse-clear"
            aria-label="Clear place selection"
            onClick={onClose}
          >
            ×
          </button>
        </div>
      </>
    );
  }

  const isLayersDialog = kind === "layers" && layersModal;
  const slotClass = [
    "map-panel-slot",
    `map-panel-slot--${kind}`,
    `map-panel-slot--${detent}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <div
        className="map-live-region-host"
        aria-live="polite"
        aria-atomic="true"
        data-testid="map-live-region"
      >
        {liveMessage || (open ? detentLabel(detent) : "")}
      </div>
      <div
        className={slotClass}
        data-testid={slotTestId}
        data-panel={kind}
        data-detent={detent}
        {...(isLayersDialog
          ? {
              role: "dialog" as const,
              "aria-modal": true as const,
              "aria-labelledby": headingId,
            }
          : {})}
      >
        <div className="map-panel-slot-chrome">
          <button
            type="button"
            className="map-panel-handle"
            aria-label={detent === "full" ? "Collapse panel" : "Expand panel"}
            aria-expanded={detent !== "peek"}
            data-testid="map-panel-handle"
            onClick={onHandleActivate}
          >
            <span className="map-panel-handle-bar" aria-hidden="true" />
          </button>
          {showSlotClose ? (
            <button
              type="button"
              className="map-panel-slot-close"
              aria-label="Close panel"
              data-testid="map-panel-slot-close"
              onClick={onRequestDismiss}
            >
              ×
            </button>
          ) : null}
        </div>
        <div
          className="map-panel-slot-scroll"
          ref={scrollRef}
          data-testid="map-panel-scroll"
        >
          <div
            id={headingId}
            tabIndex={kind === "place" ? 0 : -1}
            className="map-panel-slot-focus"
            aria-label={kind === "place" ? "Place panel" : undefined}
          >
            {children}
          </div>
        </div>
      </div>
    </>
  );
}

export function nextDetentDown(detent: PanelDetent): PanelDetent | "close" {
  const idx = DETENT_ORDER.indexOf(detent);
  if (idx <= 0) return "close";
  return DETENT_ORDER[idx - 1]!;
}

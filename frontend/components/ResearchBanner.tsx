"use client";

import { useEffect, useId, useState } from "react";

import {
  RESEARCH_BANNER_BODY,
  RESEARCH_BANNER_LEAD,
} from "@/lib/siteNav";

const DISMISS_KEY = "scot-land-research-banner-dismissed";

/** SW-016: one-line strip (tap to expand) at this width and below. */
export const RESEARCH_BANNER_STRIP_MAX_PX = 768;

export type ResearchBannerProps = {
  /** Map strip can be dismissed for the session. */
  dismissible?: boolean;
};

/**
 * One research-estimate banner per page (site rewrite item 8).
 * Exact wording from the approved rewrite spec.
 * SW-016: ≤768px → one-line strip under the header; tap to expand.
 */
export default function ResearchBanner({
  dismissible = false,
}: ResearchBannerProps) {
  const bodyId = useId();
  const [hidden, setHidden] = useState(false);
  const [stripMode, setStripMode] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!dismissible) return;
    try {
      if (sessionStorage.getItem(DISMISS_KEY) === "1") setHidden(true);
    } catch {
      /* ignore */
    }
  }, [dismissible]);

  useEffect(() => {
    const mq = window.matchMedia(
      `(max-width: ${RESEARCH_BANNER_STRIP_MAX_PX}px)`,
    );
    const sync = () => {
      const matches = mq.matches;
      setStripMode(matches);
      if (!matches) setExpanded(false);
    };
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  // SW-016: expanded strip must not cover the place card — collapse when open.
  useEffect(() => {
    if (!stripMode) return;
    const shell = document.querySelector(".app-shell");
    if (!shell) return;
    const syncPlace = () => {
      if (shell.classList.contains("place-open")) setExpanded(false);
    };
    syncPlace();
    const observer = new MutationObserver(syncPlace);
    observer.observe(shell, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, [stripMode]);

  if (hidden) return null;

  const stripCollapsed = stripMode && !expanded;
  const className = [
    "research-banner",
    dismissible ? "research-banner-map" : "research-banner-page",
    stripMode ? "research-banner-strip" : null,
    stripCollapsed ? "research-banner-collapsed" : null,
    stripMode && expanded ? "research-banner-expanded" : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <aside
      className={className}
      role="status"
      data-testid="research-banner"
      data-strip={stripMode ? "true" : "false"}
      data-expanded={stripMode ? (expanded ? "true" : "false") : "n/a"}
    >
      {stripMode ? (
        <button
          type="button"
          className="research-banner-toggle"
          data-testid="research-banner-toggle"
          aria-expanded={expanded}
          aria-controls={bodyId}
          onClick={() => {
            const placeOpen = document
              .querySelector(".app-shell")
              ?.classList.contains("place-open");
            // Keep the strip collapsed while a place card is open.
            if (placeOpen) {
              setExpanded(false);
              return;
            }
            setExpanded((value) => !value);
          }}
        >
          <span className="research-banner-text">
            <strong>{RESEARCH_BANNER_LEAD}</strong>
            <span
              id={bodyId}
              className="research-banner-body"
              hidden={stripCollapsed}
            >
              {" "}
              {RESEARCH_BANNER_BODY}
            </span>
          </span>
          <span className="research-banner-chevron" aria-hidden="true">
            {expanded ? "▴" : "▾"}
          </span>
        </button>
      ) : (
        <p className="research-banner-text">
          <strong>{RESEARCH_BANNER_LEAD}</strong> {RESEARCH_BANNER_BODY}
        </p>
      )}
      {dismissible ? (
        <button
          type="button"
          className="research-banner-dismiss"
          data-testid="research-banner-dismiss"
          aria-label="Dismiss research estimate notice"
          onClick={() => {
            try {
              sessionStorage.setItem(DISMISS_KEY, "1");
            } catch {
              /* ignore */
            }
            setHidden(true);
          }}
        >
          ×
        </button>
      ) : null}
    </aside>
  );
}

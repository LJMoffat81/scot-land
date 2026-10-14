"use client";

import { useEffect, useState } from "react";

import {
  METHODOLOGY_RESEARCH_BANNER_BODY,
  RESEARCH_BANNER_BODY,
  RESEARCH_BANNER_LEAD,
  RESEARCH_BANNER_STRIP_COLLAPSED,
} from "@/lib/siteNav";

import "./research-banner.css";

const DISMISS_KEY = "scot-land-research-banner-dismissed";
/** SW-016: one-line strip under the header up to this width. */
const STRIP_MAX_PX = 768;

export type ResearchBannerVariant = "default" | "methodology";

export type ResearchBannerProps = {
  /** Map strip can be dismissed for the session. */
  dismissible?: boolean;
  /** Use methodology-only copy (includes "experimental"). */
  variant?: ResearchBannerVariant;
};

function bannerBody(variant: ResearchBannerVariant): string {
  switch (variant) {
    case "methodology":
      return METHODOLOGY_RESEARCH_BANNER_BODY;
    case "default":
      return RESEARCH_BANNER_BODY;
    default: {
      const _exhaustive: never = variant;
      return _exhaustive;
    }
  }
}

/**
 * One research-estimate banner per page (site rewrite item 8).
 * Exact wording from the approved rewrite spec.
 * SW-016: ≤768px becomes a one-line strip you tap to expand.
 * Expanded body follows `variant` (/methodology keeps experimental).
 */
export default function ResearchBanner({
  dismissible = false,
  variant = "default",
}: ResearchBannerProps) {
  const [hidden, setHidden] = useState(false);
  const [strip, setStrip] = useState(false);
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
    const mq = window.matchMedia(`(max-width: ${STRIP_MAX_PX}px)`);
    const sync = () => {
      const match = mq.matches;
      setStrip(match);
      if (!match) setExpanded(false);
    };
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  if (hidden) return null;

  const body = bannerBody(variant);
  const showBody = !strip || expanded;
  const className = [
    "research-banner",
    dismissible ? "research-banner-map" : "research-banner-page",
    "research-banner-collapsible",
    strip ? "research-banner-strip" : "",
    strip && expanded ? "research-banner-expanded" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const text =
    strip && !expanded ? (
      <p className="research-banner-text">{RESEARCH_BANNER_STRIP_COLLAPSED}</p>
    ) : (
      <p className="research-banner-text">
        <strong>{RESEARCH_BANNER_LEAD}</strong>
        {showBody ? (
          <span className="research-banner-body"> {body}</span>
        ) : null}
      </p>
    );

  return (
    <aside
      className={className}
      role="status"
      data-testid="research-banner"
      data-banner-variant={variant}
      data-strip={strip ? "1" : "0"}
      data-expanded={strip && expanded ? "1" : "0"}
    >
      {strip ? (
        <button
          type="button"
          className="research-banner-toggle"
          data-testid="research-banner-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          {text}
        </button>
      ) : (
        text
      )}
      {dismissible && (!strip || expanded) ? (
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

"use client";

import { useEffect, useState } from "react";

import {
  METHODOLOGY_RESEARCH_BANNER_BODY,
  RESEARCH_BANNER_BODY,
  RESEARCH_BANNER_LEAD,
} from "@/lib/siteNav";

const DISMISS_KEY = "scot-land-research-banner-dismissed";

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
 */
export default function ResearchBanner({
  dismissible = false,
  variant = "default",
}: ResearchBannerProps) {
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    if (!dismissible) return;
    try {
      if (sessionStorage.getItem(DISMISS_KEY) === "1") setHidden(true);
    } catch {
      /* ignore */
    }
  }, [dismissible]);

  if (hidden) return null;

  const body = bannerBody(variant);

  return (
    <aside
      className={
        dismissible
          ? "research-banner research-banner-map"
          : "research-banner research-banner-page"
      }
      role="status"
      data-testid="research-banner"
      data-banner-variant={variant}
    >
      <p className="research-banner-text">
        <strong>{RESEARCH_BANNER_LEAD}</strong> {body}
      </p>
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

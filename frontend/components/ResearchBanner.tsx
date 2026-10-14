"use client";

import { useEffect, useState } from "react";

import {
  RESEARCH_BANNER_BODY,
  RESEARCH_BANNER_LEAD,
} from "@/lib/siteNav";

const DISMISS_KEY = "scot-land-research-banner-dismissed";

export type ResearchBannerProps = {
  /** Map strip can be dismissed for the session. */
  dismissible?: boolean;
};

/**
 * One research-estimate banner per page (site rewrite item 8).
 * Exact wording from the approved rewrite spec.
 */
export default function ResearchBanner({
  dismissible = false,
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

  return (
    <aside
      className={
        dismissible
          ? "research-banner research-banner-map"
          : "research-banner research-banner-page"
      }
      role="status"
      data-testid="research-banner"
    >
      <p className="research-banner-text">
        <strong>{RESEARCH_BANNER_LEAD}</strong> {RESEARCH_BANNER_BODY}
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

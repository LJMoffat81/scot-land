"use client";

import { useEffect, useState } from "react";

import {
  fetchGbpLiveSettings,
  GBP_LIVE_EARLY_BANNER,
  GBP_LIVE_YIELD_UP_TO,
} from "@/lib/gbpLive";

/**
 * GBP-LIVE early-estimates banner + yield "up to" line for How it works.
 * Renders nothing when the flag is OFF (default) so static HTML stays £-free.
 */
export default function GbpLiveBannerNote() {
  const [enabled, setEnabled] = useState(false);
  const [banner, setBanner] = useState(GBP_LIVE_EARLY_BANNER);
  const [yieldWording, setYieldWording] = useState(GBP_LIVE_YIELD_UP_TO);

  useEffect(() => {
    let cancelled = false;
    void fetchGbpLiveSettings().then((settings) => {
      if (cancelled) return;
      setEnabled(Boolean(settings.enabled));
      if (settings.banner) setBanner(settings.banner);
      if (settings.yield_wording) setYieldWording(settings.yield_wording);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!enabled) return null;

  return (
    <div className="gbp-live-note" data-testid="gbp-live-how-it-works">
      <p
        className="gbp-live-early-banner"
        data-testid="gbp-live-early-banner"
        role="status"
      >
        {banner}
      </p>
      <p data-testid="gbp-live-yield-wording">
        Land value is turned into a yearly rent using a yield of {yieldWording}.
        Every figure is for a Data Zone only; we do not publish a Scotland total
        here. Each figure carries an estimate label (Measured, Partly estimated,
        or Fully estimated). Placeholder figures are hidden.
      </p>
    </div>
  );
}

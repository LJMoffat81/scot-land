"use client";

import { useEffect, useState } from "react";

import {
  fetchGbpLiveSettings,
  GBP_LIVE_EARLY_BANNER,
  GBP_LIVE_RENT_RATE_HOW_IT_WORKS,
  GBP_LIVE_UNIT_WORDING,
} from "@/lib/gbpLive";

/**
 * GBP-LIVE early-estimates banner + rent-rate line for How it works.
 * Renders nothing when the flag is OFF (default) so static HTML stays £-free.
 */
export default function GbpLiveBannerNote() {
  const [enabled, setEnabled] = useState(false);
  const [banner, setBanner] = useState(GBP_LIVE_EARLY_BANNER);
  const [rentRateWording, setRentRateWording] = useState(
    GBP_LIVE_RENT_RATE_HOW_IT_WORKS,
  );
  // V1c: exact on-screen unit label (constant includes £; API omits the glyph).
  const unitWording = GBP_LIVE_UNIT_WORDING;

  useEffect(() => {
    let cancelled = false;
    void fetchGbpLiveSettings().then((settings) => {
      if (cancelled) return;
      setEnabled(Boolean(settings.enabled));
      if (settings.banner) setBanner(settings.banner);
      if (settings.rent_rate_wording) {
        setRentRateWording(settings.rent_rate_wording);
      }
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
      <p data-testid="gbp-live-rent-rate-wording">{rentRateWording}</p>
      <p data-testid="gbp-live-unit-wording">
        Figures are shown as {unitWording}, with a low–high range, a most likely
        central figure, and an estimate label.
      </p>
      <p>
        Every figure is for a Data Zone only; we do not publish a Scotland total
        here. Each figure carries an estimate label (Measured, Partly estimated,
        or Fully estimated). Placeholder figures are hidden.
      </p>
    </div>
  );
}

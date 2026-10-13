import type { Metadata } from "next";

import InternalTaxScenarioView from "@/components/InternalTaxScenarioView";

export const metadata: Metadata = {
  title: "Internal tax scenarios (blocked) | Scot-LAND",
  robots: { index: false, follow: false },
};

/**
 * Internal blocked page — structure only. No hard-coded demo £ amounts.
 * Live figures come from the internal API when Valuation unblocks.
 * Route is gated by app/internal/layout.tsx (NEXT_PUBLIC_ENABLE_INTERNAL_UI=1).
 */
export default function InternalTaxScenarioPage() {
  return (
    <main style={{ maxWidth: 720, margin: "2rem auto", padding: "0 1rem" }}>
      <h1>Scot-LAND</h1>
      <p>
        HOLD draft — internal tax scenario tools. Approved defaults (v0.1, Oct 2026)
        S1 / S2 / S3. Figures are blocked until Valuation re-passes. No £ rent
        figures go public. This page does not embed demo amounts.
      </p>
      <InternalTaxScenarioView zones={[]} scenarioId="S2" />
    </main>
  );
}

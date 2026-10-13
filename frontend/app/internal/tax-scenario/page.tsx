import type { Metadata } from "next";

import InternalTaxScenarioView, {
  type InternalZoneScenario,
} from "@/components/InternalTaxScenarioView";

export const metadata: Metadata = {
  title: "Internal tax scenarios (blocked) | Scot-LAND",
  robots: { index: false, follow: false },
};

/**
 * Demo fixture for the internal blocked page — not live API £.
 * Proves triples + market/proxy/shadow tags render. Never a public route.
 */
const DEMO_ZONES: InternalZoneScenario[] = [
  {
    code: "S01010117",
    la_name: "Glasgow City",
    value_tier: "proxy",
    tag: "proxy",
    taxable: true,
    measured_rent_gbp: { low: 8860, central: 10000, high: 10022 },
    illustrated_collection_gbp: { low: 4430, central: 5000, high: 5011 },
  },
  {
    code: "S01008677",
    la_name: "City of Edinburgh",
    value_tier: "market",
    tag: "market",
    taxable: true,
    measured_rent_gbp: { low: 17720, central: 20000, high: 20045 },
    illustrated_collection_gbp: { low: 8860, central: 10000, high: 10022 },
  },
  {
    code: "S01008678",
    la_name: "City of Edinburgh",
    value_tier: "shadow",
    tag: "shadow",
    taxable: false,
    measured_rent_gbp: { low: 4430, central: 5000, high: 5011 },
    illustrated_collection_gbp: { low: 0, central: 0, high: 0 },
  },
];

export default function InternalTaxScenarioPage() {
  return (
    <main style={{ maxWidth: 720, margin: "2rem auto", padding: "0 1rem" }}>
      <h1>Scot-LAND</h1>
      <p>
        HOLD draft — internal tax scenario tools. Approved defaults (v0.1, Oct 2026) S1 / S2 / S3.
        Figures are blocked until Valuation re-passes. No £ rent figures go
        public.
      </p>
      <InternalTaxScenarioView zones={DEMO_ZONES} scenarioId="S2" />
    </main>
  );
}

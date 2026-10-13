"use client";

import ConfidenceTag, {
  type ConfidenceTagKind,
} from "@/components/ConfidenceTag";

type MoneyTriple = { low: number; central: number; high: number };

export type InternalZoneScenario = {
  code: string;
  la_name: string;
  value_tier: ConfidenceTagKind;
  tag: ConfidenceTagKind;
  taxable: boolean;
  measured_rent_gbp: MoneyTriple;
  illustrated_collection_gbp: MoneyTriple;
};

function gbpTriple(t: MoneyTriple): string {
  const fmt = (n: number) =>
    `£${n.toLocaleString("en-GB", { maximumFractionDigits: 0 })}`;
  return `${fmt(t.low)} / ${fmt(t.central)} / ${fmt(t.high)}`;
}

/**
 * INTERNAL ONLY — blocked approved-defaults (v0.1) viewer.
 * Not mounted on public WealthInspector. No public £ rent figures.
 */
export default function InternalTaxScenarioView({
  zones,
  scenarioId,
}: {
  zones: InternalZoneScenario[];
  scenarioId: "S1" | "S2" | "S3";
}) {
  return (
    <section
      className="internal-tax-scenario"
      data-testid="internal-tax-scenario"
      data-publication-status="blocked"
      data-approved-defaults="v0.1"
    >
      <p className="internal-tax-banner" role="status">
        INTERNAL · publication_status=blocked · approved defaults (v0.1, Oct
        2026). No public £. Data Zone grain only while blocked; council views
        are counts. Shadow never taxed.
      </p>
      <h2>Tax scenario {scenarioId}</h2>
      <p>
        Every £ field is low / central / high. Tags are market / proxy / shadow.
      </p>
      <ul className="internal-tax-zone-list">
        {zones.map((z) => (
          <li key={z.code} data-zone={z.code} data-value-tier={z.value_tier}>
            <div className="internal-tax-zone-head">
              <strong>{z.code}</strong>
              <span>{z.la_name}</span>
              <ConfidenceTag kind={z.tag} />
              {!z.taxable ? <span data-testid="not-taxed">not taxed</span> : null}
            </div>
            <dl>
              <div>
                <dt>Measured rent (low / central / high)</dt>
                <dd data-testid="measured-rent-triple">
                  {gbpTriple(z.measured_rent_gbp)}
                </dd>
              </div>
              <div>
                <dt>Illustrated collection (low / central / high)</dt>
                <dd data-testid="collection-triple">
                  {gbpTriple(z.illustrated_collection_gbp)}
                </dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </section>
  );
}

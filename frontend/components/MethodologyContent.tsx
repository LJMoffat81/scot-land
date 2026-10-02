"use client";

import { useEffect, useState } from "react";

import { apiJson, getApiBaseUrl } from "../lib/api";

type Signoff = {
  status: string;
  signed_by: string | null;
  signed_at: string | null;
  organisation: string;
  notes: string;
};

type LineageEntry = {
  id: string;
  name: string;
  role: string;
  summary: string;
  url?: string;
};

type AgrConfig = {
  economist_signoff?: Signoff;
  lineage?: {
    core: LineageEntry[];
    satellite: LineageEntry[];
  };
  equal_share?: {
    enabled: boolean;
    scotland_population: number;
    notes: string;
  };
  integrity?: {
    estimate_kind: string;
    estimate_label: string;
    macro_pool_label: string;
    caveats: string[];
  };
  macro: {
    rent_share_of_gdp: number;
    scotland_income_tax_replacement_gbp: number;
    estimated_scotland_annual_rent_gbp: number;
    growth_boost_percentage_points: number;
    atcor?: boolean;
    ebcor?: boolean;
  };
  valuation: {
    primary_method: string;
    yield_rate: number;
    typical_dwelling_sqm: number;
  };
  site_share: {
    residential_wightman: number;
    residential_slrg: number;
    use_slrg_for_display: boolean;
  };
  despeculation: {
    farmland_market_to_productive: number;
    urban_speculation_discount: number;
  };
  per_square: {
    area_sqm: number;
  };
  scenarios: Record<string, { label: string; capture_rate?: number; rate_per_pound?: number }>;
};

function formatGbp(value: number) {
  if (value >= 1_000_000_000) {
    return `£${(value / 1_000_000_000).toFixed(1)}bn`;
  }
  return `£${value.toLocaleString("en-GB")}`;
}

export default function MethodologyContent() {
  const [config, setConfig] = useState<AgrConfig | null>(null);
  const [signoff, setSignoff] = useState<Signoff | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void apiJson<Signoff>("/signoff")
      .then(setSignoff)
      .catch(() => undefined);

    void apiJson<AgrConfig>("/config")
      .then(setConfig)
      .catch((err: Error) =>
        setError(
          err.message ||
            `Could not load configuration from ${getApiBaseUrl()}`,
        ),
      );
  }, []);

  const siteShare = config
    ? config.site_share.use_slrg_for_display
      ? config.site_share.residential_slrg
      : config.site_share.residential_wightman
    : null;

  const equalSharePerPerson =
    config?.equal_share?.enabled && config.equal_share.scotland_population > 0
      ? config.macro.estimated_scotland_annual_rent_gbp /
        config.equal_share.scotland_population
      : null;

  return (
    <main className="methodology-page">
      <p className="meta" style={{ marginBottom: "0.5rem" }}>
        <a href="/">Map</a>
        {" · "}
        <a href="/downloads">Downloads</a>
        {" · "}
        <a href="/open-api">Public API</a>
      </p>
      <h1>Methodology</h1>
      <p>
        Scotland Open Land estimates Annual Ground Rent (AGR) for each What3Words
        3×3 metre square (9 m²) using a <strong>valuer residual roll</strong>: market
        value − DRC of buildings (Wightman), Pickard economic base, then 5% yield,
        plus Sandilands policy scenarios. The wider intellectual lineage explains what
        ground-rent is and why the community may claim it.
      </p>
      <p className="integrity-banner" role="note">
        {config?.integrity?.estimate_label ?? "Map residual AGR (research)"} is not an
        official tax bill. The Sandilands national rent pool is a separate macro concept —
        map squares are not calibrated to sum to that pool.
      </p>
      <p>
        On the map, &ldquo;Listed taxes&rdquo; means the research basket of Scottish
        income tax, Council Tax and non-domestic rates. It is not every tax, and it
        does not say which of those the current Parliament can replace.
      </p>

      <section>
        <h2>Two rent concepts</h2>
        <ul>
          <li>
            <strong>{config?.integrity?.estimate_label ?? "Map residual AGR"}</strong> —
            Wightman residual proxy → Pickard de-speculation → yield. Used for per-square
            full AGR and as the base that scenarios scale.
          </li>
          <li>
            <strong>
              {config?.integrity?.macro_pool_label ?? "National rent pool (Sandilands)"}
            </strong>{" "}
            (
            {config
              ? formatGbp(config.macro.estimated_scotland_annual_rent_gbp)
              : "…"}
            /year) — used for equal-share illustration and the income-tax scale factor only.
          </li>
        </ul>
      </section>

      <section>
        <h2>Integrity &amp; limitations</h2>
        {config?.integrity?.caveats ? (
          <ul>
            {config.integrity.caveats.map((caveat) => (
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        ) : (
          <p className="meta">
            Caveats load from API config (<code>integrity.caveats</code>) when the backend
            is online.
          </p>
        )}
      </section>

      <section>
        <h2>Intellectual lineage</h2>
        <p className="meta">
          Pedagogical layers only — they do not replace residual / de-speculation maths.
        </p>
        {config?.lineage?.core ? (
          <ol className="lineage-list">
            {config.lineage.core.map((entry) => (
              <li key={entry.id}>
                <strong>
                  {entry.url ? (
                    <a href={entry.url} target="_blank" rel="noreferrer">
                      {entry.name}
                    </a>
                  ) : (
                    entry.name
                  )}
                </strong>{" "}
                — {entry.summary}
              </li>
            ))}
          </ol>
        ) : (
          <p className="meta">Lineage loads from API config when the backend is online.</p>
        )}
        {config?.lineage?.satellite && config.lineage.satellite.length > 0 && (
          <>
            <h3>Also see</h3>
            <ul>
              {config.lineage.satellite.map((entry) => (
                <li key={entry.id}>
                  <strong>
                    {entry.url ? (
                      <a href={entry.url} target="_blank" rel="noreferrer">
                        {entry.name}
                      </a>
                    ) : (
                      entry.name
                    )}
                  </strong>{" "}
                  — {entry.summary}
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="meta">
          Next valuation step: sales-based mass appraisal (
          <a href="https://www.openavmkit.com/" target="_blank" rel="noreferrer">
            OpenAVMKit
          </a>
          ) — see <code>docs/valuation-roadmap.md</code>.
        </p>
      </section>

      <section>
        <h2>1. Operational — Roger Sandilands (macro)</h2>
        <ul>
          <li>
            True economic rent is approximately{" "}
            {config ? `${(config.macro.rent_share_of_gdp * 100).toFixed(0)}%` : "…"} of
            GDP, not the ~£417m shown in official accounts.
          </li>
          <li>
            <strong>Gaffney ATCOR</strong>
            {config?.macro.atcor ? " (enabled in config)" : ""}: taxes on wages and
            profits ultimately load onto land rent; Sandilands applies the Scotland
            income-tax replacement case.
          </li>
          <li>
            Replacing Scotland Income Tax could raise{" "}
            {config
              ? formatGbp(config.macro.scotland_income_tax_replacement_gbp)
              : "…"}{" "}
            and add ~
            {config
              ? `${config.macro.growth_boost_percentage_points}%`
              : "…"}{" "}
            GDP growth (zero deadweight loss on pure land rent).
          </li>
        </ul>
      </section>

      <section>
        <h2>2. Operational — Andy Wightman (valuer residual)</h2>
        <p>Urban sites use a residual roll assessment:</p>
        <pre className="formula">
          {`site_capital_market = MV − DRC(improvements)
site_capital_economic = site_capital_market × Pickard_factor
annual_rent = site_capital_economic × yield`}
        </pre>
        <ul>
          <li>
            MV = council HPI average dwelling; DRC = rebuild £/m² × floor area × region ×
            stock remaining factor (default 55%).
          </li>
          <li>
            HABU = existing authorised use; hope value excluded from assessment basis.
          </li>
          <li>
            Implied land share is an output of residual (not a fixed{" "}
            {siteShare ? `${(siteShare * 100).toFixed(0)}%` : "60%"} input). Yield:{" "}
            {config ? `${(config.valuation.yield_rate * 100).toFixed(1)}%` : "5%"}.
          </li>
          <li>Rural councils: productive land-use capital × Pickard farmland factor.</li>
        </ul>
      </section>

      <section>
        <h2>3. Operational — Duncan Pickard (de-speculation)</h2>
        <ul>
          <li>
            Urban discount:{" "}
            {config
              ? `${(config.despeculation.urban_speculation_discount * 100).toFixed(0)}%`
              : "…"}{" "}
            of market-implied site value (Harrison: speculative land cycles).
          </li>
          <li>
            Farmland discount:{" "}
            {config
              ? `${(config.despeculation.farmland_market_to_productive * 100).toFixed(0)}%`
              : "…"}{" "}
            (productive value, not speculative market price).
          </li>
          <li>
            Stiglitz: public amenity and infrastructure raise land values — the rent
            this map measures is largely community-created.
          </li>
          <li>
            Macfarlane: most of a home&apos;s price is land/location, not construction.
          </li>
        </ul>
      </section>

      <section>
        <h2>Equal-share illustration (Ogilvie / Paine / Unitism)</h2>
        <p>
          Each cell&apos;s economic rent is shown as a fraction of one Scot&apos;s equal
          annual claim on the national rent pool (framing only). That claim could fund
          public services or a citizen dividend (Unitism / Paine), without changing the
          residual maths.
        </p>
        <pre className="formula">
          {`equal_share_per_person = rent_pool ÷ population
square_share = economic_rent_of_square ÷ equal_share_per_person`}
        </pre>
        <ul>
          <li>
            Rent pool:{" "}
            {config
              ? formatGbp(config.macro.estimated_scotland_annual_rent_gbp)
              : "…"}
          </li>
          <li>
            Population:{" "}
            {config?.equal_share?.scotland_population
              ? config.equal_share.scotland_population.toLocaleString("en-GB")
              : "…"}
          </li>
          <li>
            Equal claim ≈{" "}
            {equalSharePerPerson
              ? `£${Math.round(equalSharePerPerson).toLocaleString("en-GB")}/person/year`
              : "…"}
          </li>
        </ul>
      </section>

      <section>
        <h2>Per-square formula</h2>
        <pre className="formula">
          {`1. Snap lat/lng to 3m grid (${config?.per_square.area_sqm ?? 9} sqm)
2. site_capital_per_sqm = residual_method(council)     [Wightman]
3. despeculated = site_capital × discount_factor         [Pickard]
4. economic_rent = despeculated × yield_rate
5. scenario_charge = policy adjustment (see below)
6. equal-share stats from national rent pool             [Ogilvie/Paine]`}
        </pre>
      </section>

      <section>
        <h2>Policy scenarios</h2>
        {error && <p className="meta">{error}</p>}
        {config && (
          <ul>
            {Object.entries(config.scenarios).map(([id, scenario]) => (
              <li key={id}>
                <strong>{scenario.label}</strong>
                {id === "full_agr" && scenario.capture_rate !== undefined && (
                  <>
                    {" "}
                    — capture {(scenario.capture_rate * 100).toFixed(0)}% of economic rent
                    (Smith–George full recovery)
                  </>
                )}
                {id === "replace_income_tax" && (
                  <>
                    {" "}
                    — scale charges to raise{" "}
                    {formatGbp(config.macro.scotland_income_tax_replacement_gbp)} from
                    an estimated{" "}
                    {formatGbp(config.macro.estimated_scotland_annual_rent_gbp)} rent
                    pool (Sandilands + Gaffney ATCOR)
                  </>
                )}
                {id === "revenue_neutral" && scenario.rate_per_pound !== undefined && (
                  <>
                    {" "}
                    — {(scenario.rate_per_pound * 100).toFixed(2)}% of de-speculated site
                    value (Wightman)
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2>Phase 3 spatial accuracy</h2>
        <ul>
          <li>Council areas resolved by boundary polygon (not nearest centroid).</li>
          <li>
            ROS INSPIRE cadastral parcels queried live via free WMS when available.
            Map layers also include council multi-metrics (plot AGR, land rent £/m²,
            HPI house prices, AGR as % of price, land share, site capital), SIMD 2020
            deprivation shares, population density, rural valuation-method outlines,
            viewport W3W cell AGR, SVDLS vacant land, and the SG public / Crown
            Estate overlay (five national bodies; not a title). Coverage, vacant /
            public / rent-band filters, and verified council planning links sit
            beside AGR. Open or residual-derived only (no portal scrape, no owners
            or sale prices on the parcel fabric).
          </li>
          <li>
            Glasgow Ward 18 (East Centre) validation case study — toggle on the map
            or call <code>/validation/glasgow-ward-18</code>.
          </li>
          <li>What3Words search activates once SLRG nonprofit API key is set.</li>
        </ul>
      </section>

      <section>
        <h2>Economist sign-off</h2>
        {signoff ? (
          <ul>
            <li>
              Status: <strong>{signoff.status}</strong>
              {signoff.signed_by ? ` — ${signoff.signed_by}` : ""}
              {signoff.signed_at ? ` (${signoff.signed_at})` : ""}
            </li>
            <li>{signoff.organisation}</li>
            <li>{signoff.notes}</li>
          </ul>
        ) : (
          <p className="meta">Sign-off status unavailable (API offline).</p>
        )}
        <p className="meta">
          Charge parameters live in <code>economist_signoff</code> / macro blocks of{" "}
          <code>data/config/agr.yaml</code>. Lineage is pedagogical. Redeploy the API
          after edits.
        </p>
      </section>

      <p className="meta">
        Research estimate — not an official tax assessment. Full write-up:{" "}
        <code>docs/methodology.md</code>.
      </p>
      <p>
        <a href="/">Back to map</a>
      </p>
    </main>
  );
}

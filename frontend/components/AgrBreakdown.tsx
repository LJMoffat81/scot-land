"use client";

import { useState } from "react";

export type ScenarioId =
  | "full_agr"
  | "replace_income_tax"
  | "revenue_neutral"
  | "replace_full_basket";

export type ScenarioCharge = {
  id: ScenarioId;
  label: string;
  annual_charge_gbp: number;
  description: string;
  effective_rate: number | null;
};

export type AgrResult = {
  annual_ground_rent_gbp: number;
  economic_annual_rent_gbp: number;
  active_scenario: ScenarioId;
  site_rental_per_sqm_gbp: number;
  site_capital_per_sqm_gbp: number;
  despeculated_site_capital_per_sqm_gbp: number;
  despeculated_site_value_gbp: number;
  site_share_used: number | null;
  yield_rate: number;
  capture_rate: number;
  confidence: string;
  method: string;
  disclaimer: string;
  notes: string[];
  council_name: string;
  council_code: string;
  average_price_gbp: number | null;
  lookup_method: string;
  parcel_id: string | null;
  parcel_area_sqm: number | null;
  ward_name: string | null;
  scenarios: Record<ScenarioId, ScenarioCharge>;
  equal_share_enabled?: boolean;
  equal_share_rent_per_person_gbp?: number | null;
  square_as_fraction_of_equal_claim?: number | null;
  scotland_population?: number | null;
  estimate_kind?: string;
  estimate_label?: string;
  site_share_source?: string;
  national_rent_pool_gbp?: number;
  integrity_caveats?: string[];
  habu?: string;
  hope_value_excluded?: boolean;
  market_value_gbp?: number | null;
  rebuild_cost_new_gbp?: number | null;
  drc_improvements_gbp?: number | null;
  site_capital_market_per_sqm_gbp?: number;
  roll_annual_rent_notional_plot_gbp?: number;
  roll_annual_rent_parcel_gbp?: number | null;
  notional_plot_sqm?: number;
  pickard_factor?: number;
  pickard_label?: string;
  sensitivity_overrides?: Record<string, number>;
};

export type SalesContext = {
  available?: boolean;
  count?: number;
  disclaimer?: string;
  comp_report?: {
    production_ready?: boolean;
    sample_count?: number;
    synthetic_count?: number;
    median_price_gbp?: number | null;
    median_implied_site_share?: number | null;
    median_site_capital_per_sqm_gbp?: number | null;
    median_annual_rent_per_sqm_gbp?: number | null;
    disclaimer?: string;
    method?: string;
  } | null;
  nearest?: Array<{
    distance_km: number;
    price_gbp: number;
    transfer_date: string;
    postcode?: string | null;
    production_eligible?: boolean;
  }>;
};

export type PlaceFiscal = {
  gross_plot_gbp: number;
  dividend_gbp: number;
  dividend_mode?: string;
  remote_credit_gbp: number;
  net_gbp: number;
  role: "net_contributor" | "net_receiver" | "net_neutral" | string;
  note?: string;
};

export type PlatformContext = {
  vacant_or_derelict?: boolean;
  parcel?: { found?: boolean; label?: string | null; inspire_id?: string | null };
  vdl?: {
    intersects?: boolean;
    sites?: Array<{
      name?: string | null;
      site_type?: string | null;
      size_ha?: number | null;
      local_authority?: string | null;
      owner_class?: string | null;
    }>;
  };
  public_or_crown?: {
    status?: string;
    on_this_point?: boolean | null;
    holdings?: Array<{
      organisation?: string | null;
      site_name?: string | null;
      area_ha?: number | null;
    }>;
    map_url?: string;
    note?: string;
  };
  local_authority_holding?: { status?: string; reason?: string };
  common_good?: { status?: string; reason?: string };
  private_or_sasine?: { status?: string; note?: string };
  registers?: {
    name?: string | null;
    planning?: { url?: string | null; label?: string | null; scope?: string };
    cat?: { url?: string | null; label?: string | null };
    land_map?: { url?: string | null; note?: string | null } | null;
    scotlis?: { url?: string | null };
  } | null;
  scotlis?: {
    public_home?: string;
    search_hint?: string;
    note?: string;
  };
  filters?: {
    vacant?: boolean;
    public_private?: string;
    value_band?: string | null;
  };
};

type Props = {
  agr: AgrResult;
  areaSqm: number;
  scenario: ScenarioId;
  onScenarioChange: (scenario: ScenarioId) => void;
  postcode?: string;
  lat: number;
  lng: number;
  what3words?: string | null;
  parcelLabel?: string | null;
  parcelAreaSqm?: number | null;
  fiscal?: PlaceFiscal | null;
  platform?: PlatformContext | null;
  onDownloadReport?: (format: "markdown" | "json") => void;
  reportDownloading?: boolean;
};

const SCENARIO_ORDER: ScenarioId[] = [
  "replace_income_tax",
  "revenue_neutral",
  "replace_full_basket",
];

const SCENARIO_SHORT: Record<ScenarioId, string> = {
  replace_full_basket: "Listed taxes",
  full_agr: "Full rent",
  replace_income_tax: "Income tax",
  revenue_neutral: "Council tax and rates",
};

function formatGbp(value: number, digits = 2) {
  return `\u00a3${value.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export default function AgrBreakdown({
  agr,
  areaSqm,
  scenario,
  onScenarioChange,
  postcode,
  lat,
  lng,
  what3words,
  parcelLabel,
  parcelAreaSqm,
  fiscal,
  platform,
  onDownloadReport,
  reportDownloading,
}: Props) {
  const active = agr.scenarios[scenario] ?? agr.scenarios.full_agr;
  const plotFull = agr.roll_annual_rent_notional_plot_gbp;
  const cellFull = agr.economic_annual_rent_gbp;
  const scale = cellFull > 0 ? active.annual_charge_gbp / cellFull : 1;
  const parcelFull =
    parcelAreaSqm != null && parcelAreaSqm > 0
      ? agr.site_rental_per_sqm_gbp * parcelAreaSqm * scale
      : agr.roll_annual_rent_parcel_gbp != null
        ? agr.roll_annual_rent_parcel_gbp * scale
        : null;
  const headline =
    fiscal?.gross_plot_gbp != null && fiscal.gross_plot_gbp > 0
      ? fiscal.gross_plot_gbp
      : parcelFull != null && parcelFull > 0
        ? parcelFull
        : plotFull != null && plotFull > 0
          ? plotFull * scale
          : active.annual_charge_gbp;
  const headlineIsParcel = parcelFull != null && parcelFull > 0 && !fiscal;
  const headlineIsPlot =
    !headlineIsParcel && plotFull != null && plotFull > 0 && !fiscal;

  const place = [postcode, agr.council_name].filter(Boolean).join(" \u00b7 ");
  const w3wClean = what3words ? what3words.replace(/^\/+/, "") : null;
  const w3wParts = w3wClean ? w3wClean.split(".") : [];
  const [copied, setCopied] = useState(false);
  const [shared, setShared] = useState(false);
  const [ownershipOpen, setOwnershipOpen] = useState(false);

  const netRole = fiscal?.role;
  const netClass =
    netRole === "net_receiver"
      ? "fiscal-net receiver"
      : netRole === "net_contributor"
        ? "fiscal-net contributor"
        : "fiscal-net";

  return (
    <div className="clarity-result">
      {w3wParts.length === 3 && (
        <div className="w3w-hero-row">
          <p className="w3w-hero" aria-label={`what3words ${w3wClean}`}>
            <span className="w3w-slash">{"///"}</span>
            {w3wParts.map((word, i) => (
              <span key={word + i}>
                {i > 0 && <span className="w3w-dot">.</span>}
                <span className="w3w-word">{word}</span>
              </span>
            ))}
          </p>
          <div className="w3w-actions">
            <button
              type="button"
              className="w3w-copy"
              title="Copy three-word address"
              onClick={() => {
                void navigator.clipboard?.writeText(`///${w3wClean}`).then(() => {
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 1600);
                });
              }}
            >
              {copied ? "Copied" : "Copy"}
            </button>
            <button
              type="button"
              className="w3w-copy"
              title="Copy a link to this place"
              onClick={() => {
                void navigator.clipboard?.writeText(window.location.href).then(
                  () => {
                    setShared(true);
                    window.setTimeout(() => setShared(false), 1600);
                  },
                );
              }}
            >
              {shared ? "Link copied" : "Share"}
            </button>
          </div>
        </div>
      )}

      <p className="location-line">
        {place || `${lat.toFixed(5)}, ${lng.toFixed(5)}`}
      </p>

      <div className="agr-value" aria-live="polite">
        {formatGbp(headline, headline >= 100 ? 0 : 2)}
        <span className="agr-unit">/year gross</span>
      </div>

      <p className="headline-caption">
        {fiscal
          ? "Research estimate for the land, not the building. Not a rates bill."
          : headlineIsParcel
            ? `Property parcel${parcelLabel ? ` ${parcelLabel}` : ""}${
                parcelAreaSqm
                  ? ` \u00b7 ${Math.round(parcelAreaSqm).toLocaleString("en-GB")} m\u00b2`
                  : ""
              }`
            : headlineIsPlot
              ? `Typical plot (~${agr.notional_plot_sqm?.toLocaleString("en-GB")} m\u00b2)`
              : `This ${areaSqm} m\u00b2 cell \u00b7 ${formatGbp(active.annual_charge_gbp)}/yr`}
      </p>

      {fiscal && (
        <div className="fiscal-place">
          <p className="ownership-heading">
            {fiscal.role === "net_receiver"
              ? `One-person comparison: receives ${formatGbp(Math.abs(fiscal.net_gbp), 0)}`
              : fiscal.role === "net_contributor"
                ? `One-person comparison: pays ${formatGbp(fiscal.net_gbp, 0)}`
                : "One-person comparison: about even"}
          </p>
          <div className="fiscal-row">
            <span>Land charge</span>
            <strong>{formatGbp(fiscal.gross_plot_gbp, 0)}</strong>
          </div>
          <div className="fiscal-row">
            <span>One person&apos;s share of the list</span>
            <strong>\u2212{formatGbp(fiscal.dividend_gbp, 0)}</strong>
          </div>
          {fiscal.remote_credit_gbp > 0 && (
            <div className="fiscal-row">
              <span>Remote / island credit</span>
              <strong>\u2212{formatGbp(fiscal.remote_credit_gbp, 0)}</strong>
            </div>
          )}
          <div className={`fiscal-row net ${netClass}`}>
            <span>{fiscal.net_gbp < 0 ? "Receives" : "Pays"}</span>
            <strong>
              {fiscal.net_gbp < 0 ? "" : "+"}
              {formatGbp(fiscal.net_gbp, 0)}
            </strong>
          </div>
          <p className="fiscal-role-tag">
            A one-person comparison for this place. Not a share of the soil,
            and not a rates bill.
          </p>
        </div>
      )}

      <div className="scenario-pills" role="tablist" aria-label="Tax replacement scenario">
        {SCENARIO_ORDER.map((id) => {
          if (!agr.scenarios[id]) return null;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={scenario === id}
              className={scenario === id ? "scenario-pill active" : "scenario-pill"}
              onClick={() => onScenarioChange(id)}
            >
              {SCENARIO_SHORT[id]}
            </button>
          );
        })}
      </div>

      {platform && (
        <div className="ownership-block">
          <button
            type="button"
            className="ownership-heading ownership-toggle"
            onClick={() => setOwnershipOpen((v) => !v)}
          >
            Who holds this land
            <span>{ownershipOpen ? "–" : "+"}</span>
          </button>
          {ownershipOpen && (
            <>
          <div className="place-flags">
            {platform.vacant_or_derelict && (
              <span className="flag vacant">Vacant / derelict survey site</span>
            )}
            {platform.public_or_crown?.on_this_point && (
              <span className="flag public">Public / Crown holding</span>
            )}
            {platform.filters?.value_band && (
              <span className={`flag band-${platform.filters.value_band}`}>
                {platform.filters.value_band} rent band
              </span>
            )}
            {platform.parcel?.found === false && (
              <span className="flag gap">No INSPIRE parcel here</span>
            )}
            {platform.filters?.public_private === "unknown" &&
              !platform.public_or_crown?.on_this_point && (
                <span className="flag gap">Ownership unknown here</span>
              )}
          </div>
          <dl className="ownership-rows">
            <div>
              <dt>Cadastre</dt>
              <dd>
                {platform.parcel?.found
                  ? platform.parcel.label ||
                    platform.parcel.inspire_id ||
                    "INSPIRE parcel (extent only)"
                  : "No INSPIRE parcel at this point"}
              </dd>
            </div>
            <div>
              <dt>Public / Crown</dt>
              <dd>
                {platform.public_or_crown?.on_this_point
                  ? [
                      platform.public_or_crown.holdings?.[0]?.organisation,
                      platform.public_or_crown.holdings?.[0]?.site_name,
                    ]
                      .filter(Boolean)
                      .join(" \u00b7 ") || "In the five-body overlay"
                  : "Not in the five-body overlay (not council land)"}
              </dd>
            </div>
            <div>
              <dt>Vacant / derelict</dt>
              <dd>
                {platform.vdl?.sites && platform.vdl.sites.length > 0
                  ? [
                      platform.vdl.sites[0].name || "SVDLS site",
                      platform.vdl.sites[0].site_type,
                    ]
                      .filter(Boolean)
                      .join(" \u00b7 ")
                  : "Not on the SVDLS survey overlay"}
              </dd>
            </div>
            <div>
              <dt>Local authority</dt>
              <dd>
                {platform.local_authority_holding?.reason ||
                  "National LA layer is not openly licensed"}
              </dd>
            </div>
            <div>
              <dt>Common Good</dt>
              <dd>
                {platform.common_good?.reason ||
                  "No single open national spatial file"}
              </dd>
            </div>
            <div>
              <dt>Private / Sasine</dt>
              <dd>
                {platform.private_or_sasine?.note ||
                  "Names stay on ScotLIS. Not invented here."}
              </dd>
            </div>
          </dl>
          {platform.registers && (
            <p className="place-note">
              {platform.registers.planning?.url && (
                <>
                  <a
                    href={platform.registers.planning.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {platform.registers.planning.scope === "council"
                      ? "Planning applications"
                      : "ePlanning Scotland"}
                  </a>
                  {" \u00b7 "}
                </>
              )}
              {platform.registers.land_map?.url && (
                <>
                  <a
                    href={platform.registers.land_map.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {platform.registers.name || "Council"} land map
                  </a>
                  {" \u00b7 "}
                </>
              )}
              {platform.registers.cat?.url && (
                <a
                  href={platform.registers.cat.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  CAT register
                </a>
              )}
            </p>
          )}
          <p className="place-note muted">
            Research overlay, not a title sheet. Confirm ownership on ScotLIS.
          </p>
            </>
          )}
        </div>
      )}

      <p className="result-links">
        <a href="/methodology">How this is calculated</a>
        {platform?.scotlis?.public_home && (
          <>
            {" \u00b7 "}
            <a
              href={platform.scotlis.public_home}
              target="_blank"
              rel="noreferrer"
              title={platform.scotlis.note}
            >
              Official title (ScotLIS)
            </a>
          </>
        )}
        {platform?.public_or_crown?.map_url && (
          <>
            {" \u00b7 "}
            <a
              href={platform.public_or_crown.map_url}
              target="_blank"
              rel="noreferrer"
            >
              Public / Crown map
            </a>
          </>
        )}
        {onDownloadReport && (
          <>
            {" \u00b7 "}
            <button
              type="button"
              className="linkish"
              disabled={reportDownloading}
              onClick={() => onDownloadReport("markdown")}
            >
              {reportDownloading ? "Preparing\u2026" : "MSP brief"}
            </button>
          </>
        )}
      </p>
    </div>
  );
}

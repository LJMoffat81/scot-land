"use client";

import { useEffect, useState } from "react";
import { apiJson, engineVersionLine, type EngineStamp } from "../lib/api";

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
  stamp?: EngineStamp | null;
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
  land_register_outline?: { status?: string; note?: string };
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
  postcode?: string;
  placeLabel?: string | null;
  lat: number;
  lng: number;
  what3words?: string | null;
  parcelLabel?: string | null;
  parcelAreaSqm?: number | null;
  fiscal?: PlaceFiscal | null;
  platform?: PlatformContext | null;
  locationClass?: string | null;
};

const CARD_DEVELOPMENT_NOTICE =
  "Figures are in development and may change as the engine improves.";

const DEVELOPMENT_NOTICE = `Research estimate. ${CARD_DEVELOPMENT_NOTICE}`;

const NOT_ON_LAND_REGISTER_LABEL = "Not yet on the Land Register";
const NOT_ON_LAND_REGISTER_NOTE =
  "We found no Land Register boundary at this point. Its title may still be in the older Sasine register, or the land may not be registered at all. We estimate it by area and land type, and show no boundaries, titles or owners.";

export function MapStampFooter() {
  const [stamp, setStamp] = useState<EngineStamp | null>(null);

  useEffect(() => {
    let active = true;
    apiJson<{ stamp?: EngineStamp | null }>("/health")
      .then((data) => {
        if (active) setStamp(data.stamp ?? null);
      })
      .catch(() => {
        if (active) setStamp(null);
      });
    return () => {
      active = false;
    };
  }, []);

  const versionLine = engineVersionLine(stamp);
  return (
    <footer className="map-footer">
      <p>{DEVELOPMENT_NOTICE}</p>
      {versionLine ? <p className="engine-stamp">{versionLine}</p> : null}
      <p className="map-footer-credit">
        <a href="/methodology">Sources and method</a>
      </p>
      <p className="map-footer-credit">
        Contains OS data © Crown copyright and database right 2026
      </p>
      <p className="map-footer-credit">
        Contains Royal Mail data © Royal Mail copyright and database right 2026
      </p>
      <p className="map-footer-credit">
        Source: Office for National Statistics licensed under the Open Government Licence v.3.0
      </p>
      <p className="map-footer-credit">No data provider endorses this site.</p>
    </footer>
  );
}

function formatGbp(value: number, digits = 2) {
  return `\u00a3${value.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export default function AgrBreakdown({
  agr,
  areaSqm,
  postcode,
  placeLabel,
  lat,
  lng,
  what3words,
  parcelLabel,
  parcelAreaSqm,
  fiscal,
  platform,
  locationClass,
}: Props) {
  const active = agr.scenarios.full_agr;
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
  const headlineIsPlot = plotFull != null && plotFull > 0;

  const place = [placeLabel, postcode, agr.council_name].filter(Boolean).join(" \u00b7 ");
  const w3wClean = what3words ? what3words.replace(/^\/+/, "") : null;
  const w3wParts = w3wClean ? w3wClean.split(".") : [];
  const [copied, setCopied] = useState(false);
  const [shared, setShared] = useState(false);
  const [outlineOpen, setOutlineOpen] = useState(false);

  const hasParcel = parcelAreaSqm != null && parcelAreaSqm > 0;
  const versionLine = engineVersionLine(agr.stamp);

  return (
    <div className="clarity-result">
      <p className="location-line">
        {place || `${lat.toFixed(5)}, ${lng.toFixed(5)}`}
      </p>
      {locationClass ? <p className="meta">Location: {locationClass}</p> : null}

      <div className="agr-value" aria-live="polite">
        {formatGbp(headline, headline >= 100 ? 0 : 2)}
        <span className="agr-unit">/year</span>
      </div>

      <p className="headline-caption">
        {hasParcel
          ? `This piece of land, ${Math.round(parcelAreaSqm as number).toLocaleString("en-GB")} m\u00b2.`
          : agr.method === "productive_land_use"
            ? "One hectare of farmland in this council."
            : headlineIsPlot
              ? `A typical home plot in this council${
                  agr.notional_plot_sqm
                    ? ` (about ${Math.round(agr.notional_plot_sqm).toLocaleString("en-GB")} m\u00b2)`
                    : ""
                }.`
              : `This ${areaSqm} m\u00b2 square.`}
        {" "}
        Land only, not the building. Research estimate, not a rates bill.
        The rate is this council&apos;s, so two parcels of the same size here have the same rent.
      </p>
      <p className="meta dev-notice">{CARD_DEVELOPMENT_NOTICE}</p>
      {versionLine ? <p className="engine-stamp">{versionLine}</p> : null}

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

      {parcelLabel ? <p className="meta">Register parcel {parcelLabel}</p> : null}

      {platform?.land_register_outline?.status === "no_outline" ? (
        <>
          <p
            className="meta"
            style={{ cursor: "help" }}
            title={NOT_ON_LAND_REGISTER_NOTE}
            role="button"
            tabIndex={0}
            aria-expanded={outlineOpen}
            onClick={() => setOutlineOpen((open) => !open)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setOutlineOpen((open) => !open);
              }
            }}
          >
            {NOT_ON_LAND_REGISTER_LABEL}
          </p>
          {outlineOpen ? <p className="meta">{NOT_ON_LAND_REGISTER_NOTE}</p> : null}
        </>
      ) : null}

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
      </p>
    </div>
  );
}

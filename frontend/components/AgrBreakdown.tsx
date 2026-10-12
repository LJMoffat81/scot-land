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
  wide_range?: boolean;
  wide_range_ratio?: number | null;
  basis?: "town" | "countryside" | string;
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
  common_good?: {
    status?: string;
    reason?: string;
    on_this_point?: boolean | null;
    national_gap?: string;
    register?: {
      url?: string | null;
      label?: string | null;
      kind?: string | null;
      name?: string | null;
    } | null;
    spatial?: {
      label?: string | null;
      metadata_url?: string | null;
      licence?: string | null;
      host_note?: string | null;
    } | null;
  };
  land_register_outline?: { status?: string; note?: string };
  private_or_sasine?: { status?: string; note?: string };
  registers?: {
    name?: string | null;
    planning?: { url?: string | null; label?: string | null; scope?: string };
    cat?: { url?: string | null; label?: string | null };
    land_map?: { url?: string | null; note?: string | null } | null;
    scotlis?: { url?: string | null };
    common_good?: {
      status?: string;
      register?: { url?: string | null; label?: string | null } | null;
    } | null;
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
  dataZone?: {
    code: string;
    name?: string;
    house_sale_median_gbp?: number | null;
    house_sale_year?: number | null;
    urban_rural_name?: string;
    urban_rural_year?: number | null;
    urban_rural_route?: string;
  } | null;
  seabedNotes?: string[] | null;
};

function zoneClassLine(
  zone: Props["dataZone"],
  countryside: boolean,
): string | null {
  if (!zone) return null;
  const name = zone.urban_rural_name?.trim();
  if (!name) return null;
  const year = zone.urban_rural_year ?? 2020;
  const point = countryside ? "countryside" : "town";
  const route = zone.urban_rural_route;
  if ((route === "town" || route === "countryside") && route !== point) {
    return `Classed ${name} in ${year}. This point is ${point}, so the figure stays on the ${point} rate.`;
  }
  return `Classed ${name} in ${year}. The yearly figure follows this point.`;
}

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
        {" · "}
        Contains OS data © Crown copyright and database right 2026
        {" · "}
        Contains Royal Mail data © Royal Mail copyright and database right 2026
        {" · "}
        Source: Office for National Statistics licensed under the Open Government Licence v.3.0
        {" · "}
        No data provider endorses this site.
      </p>
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
  dataZone,
  seabedNotes,
}: Props) {
  const active = agr.scenarios.full_agr;
  const plotFull = agr.roll_annual_rent_notional_plot_gbp;
  const cellFull = agr.economic_annual_rent_gbp;
  const scale = cellFull > 0 ? active.annual_charge_gbp / cellFull : 1;
  const parcelFull =
    agr.roll_annual_rent_parcel_gbp != null
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

  const place = [placeLabel, postcode, agr.council_name].filter(Boolean).join(" \u00b7 ");
  const w3wClean = what3words ? what3words.replace(/^\/+/, "") : null;
  const w3wParts = w3wClean ? w3wClean.split(".") : [];
  const [copied, setCopied] = useState(false);
  const [shared, setShared] = useState(false);
  const [outlineOpen, setOutlineOpen] = useState(false);

  const hasParcel = parcelAreaSqm != null && parcelAreaSqm > 0;
  const countryside = agr.basis === "countryside" || agr.method === "productive_land_use";
  const versionLine = engineVersionLine(agr.stamp);
  const pieceSqm = hasParcel ? Math.round(parcelAreaSqm as number) : null;
  const plotSqm = agr.notional_plot_sqm ? Math.round(agr.notional_plot_sqm) : null;
  const figureLine = hasParcel
    ? countryside
      ? `This piece of countryside, ${pieceSqm!.toLocaleString("en-GB")} m\u00b2.`
      : `This piece of town land, ${pieceSqm!.toLocaleString("en-GB")} m\u00b2.`
    : countryside
      ? "Countryside: one hectare of farmland."
      : `Town: one home plot${
          plotSqm ? `, about ${plotSqm.toLocaleString("en-GB")} m\u00b2` : ""
        }.`;
  const rateLine = hasParcel
    ? countryside
      ? "Two pieces of the same size on this countryside rate match. A town parcel in this council uses the town rate."
      : "Two pieces of the same size on this town rate match. Countryside in this council uses a different rate."
    : countryside
      ? "No register outline here, so this is one hectare at the countryside rate. The map colour is the town home plot, not this number."
      : "No register outline here, so this is one home plot at the town rate. Countryside in this council uses a different rate.";
  const classLine = zoneClassLine(dataZone, countryside);

  return (
    <div className="clarity-result">
      <p className="location-line">
        {place || `${lat.toFixed(5)}, ${lng.toFixed(5)}`}
      </p>
      {locationClass ? <p className="meta">Location: {locationClass}</p> : null}
      {dataZone?.code ? (
        <p className="meta">
          Data zone {dataZone.code}
          {dataZone.name ? `, ${dataZone.name}` : ""}
        </p>
      ) : null}
      {classLine ? <p className="meta">{classLine}</p> : null}

      <div className="agr-value" aria-live="polite">
        {formatGbp(headline, headline >= 100 ? 0 : 2)}
        <span className="agr-unit">/year</span>
      </div>

      <p className="headline-caption figure-line">{figureLine}</p>
      {agr.wide_range ? (
        <p className="headline-caption">
          Homes here sell for close to what they&apos;d cost to rebuild, so the land figure is less certain than most.
        </p>
      ) : null}

      <p className="headline-caption">
        Land only, not the building. Research estimate, not a rates bill. {rateLine}
      </p>
      {!countryside ? (
        <p className="headline-caption">
          The town price is the data zone median house sale, building included. A larger piece of land follows a diminishing area rule.
        </p>
      ) : null}
      {!countryside && plotFull === 0 ? (
        <p className="headline-caption">The residual is at or below the margin.</p>
      ) : null}
      {seabedNotes && seabedNotes.length > 0 ? (
        <>
          <p className="headline-caption">
            The seabed here is leased. This note is separate from the figure above.
          </p>
          {seabedNotes.map((note, index) => (
            <p key={`${index}-${note.slice(0, 24)}`} className="meta">
              {note}
            </p>
          ))}
        </>
      ) : null}
      {dataZone?.house_sale_median_gbp != null && dataZone.house_sale_median_gbp > 0 ? (
        <p className="meta">
          House sales in this data zone, median{" "}
          {formatGbp(dataZone.house_sale_median_gbp, 0)} in{" "}
          {dataZone.house_sale_year ?? 2023}. The building is included. Not the land charge.
        </p>
      ) : null}
      <p className="result-links">
        <a href="/methodology#how-sure">How sure is this?</a>
      </p>
      <p className="meta dev-notice">{CARD_DEVELOPMENT_NOTICE}</p>
      {versionLine ? <p className="engine-stamp">{versionLine}</p> : null}

      {w3wParts.length === 3 && (
        <div className="w3w-hero-row">
          <p className="w3w-hero" aria-label={`Scot-LAND square ${w3wClean}`}>
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
              title="Copy Scot-LAND square address"
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
      {platform?.parcel?.inspire_id ? (
        <p className="meta">INSPIRE id {platform.parcel.inspire_id}</p>
      ) : null}
      {platform?.public_or_crown?.on_this_point &&
      platform.public_or_crown.holdings &&
      platform.public_or_crown.holdings.length > 0 ? (
        <p className="meta">
          Public land owner type:{" "}
          {platform.public_or_crown.holdings
            .map((h) => h.organisation)
            .filter(Boolean)
            .join(", ")}
          {" · "}
          overlay source, not a title
        </p>
      ) : null}

      {platform?.common_good ? (
        <p className="meta">
          Common Good:{" "}
          {platform.common_good.status === "linked" ? "linked register" : "gap"}
          {platform.common_good.register?.url ? (
            <>
              {" · "}
              <a
                href={platform.common_good.register.url}
                target="_blank"
                rel="noreferrer"
              >
                {platform.common_good.register.label || "council register"}
              </a>
            </>
          ) : null}
          {platform.common_good.spatial?.metadata_url ? (
            <>
              {" · "}
              <a
                href={platform.common_good.spatial.metadata_url}
                target="_blank"
                rel="noreferrer"
              >
                {platform.common_good.spatial.label || "spatial metadata"}
              </a>
            </>
          ) : null}
          {" · "}
          no national open map layer; not a title
        </p>
      ) : null}

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

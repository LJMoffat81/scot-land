import React, { useEffect, useState } from "react";

import QualityTag from "./QualityTag";
import type {
  ApiFailure,
  DataZoneLookup,
  DisplayView,
  TierTotal,
  ValueTier,
  ViewId,
  WealthComponent,
  WealthResponse,
} from "../lib/useWealthApi";
import { isQualityTag } from "../lib/qualityTag";
import { TaxScenarioPanel } from "./TaxScenarioPanel";

export interface WealthInspectorData {
  zone: DataZoneLookup;
  wealth: WealthResponse;
}

interface WealthInspectorProps {
  isOpen: boolean;
  onClose: () => void;
  data: WealthInspectorData | null;
  failure?: ApiFailure | null;
  isLoading: boolean;
}

const TIER_LABEL: Record<ValueTier, string> = {
  market: "Market (observed rents)",
  proxy: "Proxy (derived from prices)",
  shadow: "Shadow (non-market values)",
};
const LAYER_LABEL: Record<WealthComponent["layer"], string> = {
  surface: "Surface (residential land)",
  extractive: "Extractive",
  eco: "Eco",
};
const VIEW_LABEL: Record<ViewId, string> = {
  per_residential_hectare: "Per hectare of residential land",
  per_dwelling: "Per dwelling",
  per_resident: "Per resident",
};
const VIEW_UNIT: Record<ViewId, string> = {
  per_residential_hectare: "/ha/yr",
  per_dwelling: "/dwelling/yr",
  per_resident: "/resident/yr",
};
const WITHHELD_LABEL: Record<string, string> = {
  blocked: "Withheld: publication blocked (failed the zone rent ceiling check). Its licence level is unchanged.",
  not_publishable: "Withheld: not cleared for public release at this level.",
  placeholder: "Not shown: placeholder data.",
  no_measured_rent: "No measured rent for this zone.",
  unknown_value_tier: "Excluded: unknown value tier.",
};
const FLAG_LABEL: Record<string, string> = {
  surface_not_found: "No surface rent row for this zone yet (not £0).",
  surface_not_measured: "Surface rent not yet measured for this zone.",
  model_filled: "Model-filled zone: too few sales to measure directly.",
  negative_residual: "Prices were below rebuild cost here; rent is floored at £0.",
  absent_from_ros_price_file: "This zone does not appear in the RoS price file.",
  dwellings_count_missing_for_price_year: "No dwelling count for this price year: per-dwelling view not shown (not taken from another year).",
  population_count_missing_for_price_year: "No population count for this price year: per-resident view not shown (not taken from another year).",
  band_incomplete: "Uncertainty band incomplete.",
};

function gbp(v: number | null | undefined, digits = 0): string {
  if (v == null) return "–";
  return `£${v.toLocaleString("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: 0 })}`;
}

function band(lo: number | null | undefined, hi: number | null | undefined, digits = 0): string | null {
  if (lo == null || hi == null) return null;
  return `${gbp(lo, digits)} – ${gbp(hi, digits)}`;
}

function failureText(f: ApiFailure): { title: string; body: string } {
  switch (f.error) {
    case "dz_boundaries_unavailable":
      return { title: "Data zone lookup unavailable", body: "Data zone boundaries are not loaded, so no zone (and no figure) is shown." };
    case "no_data_zone_at_point":
      return { title: "No data zone here", body: "This point is not inside a Scottish data zone (e.g. at sea)." };
    case "wealth_database_unavailable":
      return { title: "Wealth database unavailable", body: "No figures returned. Nothing has been estimated in their place." };
    case "invalid_zone_id":
    case "zone_out_of_range":
    case "vintage_mismatch":
      return { title: "Zone not recognised", body: f.message };
    case "mixed_price_years":
      return {
        title: "Totals refused",
        body: `Rents priced in different years (${(f.price_years ?? []).join(", ")}) cannot be added. No total is shown.`,
      };
    case "network_error":
      return { title: "Could not reach the API", body: f.message };
    default:
      if (f.status === 400) return { title: "Outside Scotland", body: f.message };
      return { title: `Request failed (${f.status || "network"})`, body: f.message };
  }
}

function ViewPanel({ views }: { views: WealthResponse["wealth"]["display"] }) {
  const [view, setView] = useState<ViewId>(views.default);
  useEffect(() => setView(views.default), [views.default]);
  const v: DisplayView = views.views[view];
  const digits = view === "per_residential_hectare" ? 0 : 2;
  return (
    <section className="space-y-2" aria-label="Surface rent views">
      <div className="flex gap-1 flex-wrap" role="tablist">
        {views.order.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={id === view}
            onClick={() => setView(id)}
            className={`text-xs px-2 py-1 rounded border ${id === view ? "bg-blue-600 text-white border-blue-600" : "border-slate-200 text-slate-600"}`}
          >
            {VIEW_LABEL[id]}
            {id === views.default ? " (default)" : ""}
          </button>
        ))}
      </div>
      <div className="bg-slate-50 p-3 rounded border border-slate-100">
        {v.status === "ok" || v.status === "interim_rough" ? (
          <>
            <p className="font-mono text-lg">
              {gbp(v.value, digits)}
              <span className="text-xs text-slate-500"> {VIEW_UNIT[view]}</span>
            </p>
            {band(v.low, v.high, digits) && <p className="text-xs text-slate-500">Range {band(v.low, v.high, digits)}</p>}
            {v.status === "interim_rough" && <p className="text-xs text-amber-700">Rough: {v.flag}</p>}
          </>
        ) : (
          <p className="text-sm text-slate-500 italic">
            {v.status === "denominator_pending"
              ? `Denominator pending (${v.denominator ?? "not loaded"}). Nothing computed.`
              : v.status === "withheld"
                ? "Withheld (see surface rent below)."
                : "No surface rent figure for this zone."}
          </p>
        )}
        {view === "per_resident" && (
          <p className="text-xs text-slate-500 mt-1">
            Second-home share:{" "}
            {v.second_home_share != null ? `${(v.second_home_share * 100).toFixed(1)}%` : "pending"}
            {v.vacant_share != null ? ` · vacant ${(v.vacant_share * 100).toFixed(1)}%` : ""}
            {v.flag && v.status === "ok" ? ` – ${v.flag}` : ""}
          </p>
        )}
      </div>
    </section>
  );
}

function ComponentRow({ c }: { c: WealthComponent }) {
  return (
    <div className="text-xs p-2 bg-slate-50 rounded border border-slate-100 space-y-1">
      <div className="flex justify-between">
        <span className="font-medium text-slate-700">
          {LAYER_LABEL[c.layer]}
          {c.name && c.layer !== "surface" ? `: ${c.name}` : ""}
        </span>
        <span className="font-mono">{c.withheld ? "withheld" : gbp(c.measured_rent_gbp)}</span>
      </div>
      {!c.withheld && band(c.uncertainty_low, c.uncertainty_high) && (
        <div className="text-slate-500">Range {band(c.uncertainty_low, c.uncertainty_high)}</div>
      )}
      <div className="text-slate-500">
        {c.value_tier ?? "?"} tier · quality{" "}
        {isQualityTag(c.quality) ? (
          <QualityTag quality={c.quality} />
        ) : (
          (c.quality ?? "?")
        )}{" "}
        · {c.publish_level ?? "?"}
        {c.price_year ? ` · ${c.price_year} prices` : ""}
        {c.evidence_year && c.evidence_year !== c.price_year ? ` (evidence ${c.evidence_year})` : ""}
        {c.model_filled ? " · model-filled" : ""}
      </div>
      {c.excluded_reason && (
        <div className={c.withheld ? "text-amber-700" : "text-slate-500"}>
          {WITHHELD_LABEL[c.excluded_reason] ?? c.excluded_reason}
          {!c.in_totals && !c.withheld ? " Not in totals." : ""}
        </div>
      )}
      {c.licence && <div className="text-slate-400">Licence: {c.licence}</div>}
    </div>
  );
}

function TierRow({ tier, t }: { tier: ValueTier; t: TierTotal }) {
  return (
    <div className="flex justify-between items-start text-sm">
      <div>
        <div className="text-slate-700">{TIER_LABEL[tier] ?? tier}</div>
        <div className="text-xs text-slate-500">
          {t.components} component{t.components === 1 ? "" : "s"}
          {t.price_year ? ` · ${t.price_year} prices` : ""}
          {t.flags.map((f) => ` · ${FLAG_LABEL[f] ?? f}`).join("")}
        </div>
      </div>
      <div className="text-right">
        <div className="font-mono font-semibold">{t.total_gbp == null ? "not summed" : `${gbp(t.total_gbp)}/yr`}</div>
        {band(t.low_gbp, t.high_gbp) && <div className="text-xs text-slate-500">{band(t.low_gbp, t.high_gbp)}</div>}
      </div>
    </div>
  );
}

export function WealthInspector({ isOpen, onClose, data, failure, isLoading }: WealthInspectorProps) {
  if (!isOpen) return null;
  const w = data?.wealth.wealth;
  const tiers = w ? (Object.entries(w.totals_by_tier) as [ValueTier, TierTotal][]) : [];
  const other = data && data.zone.dz2011 && data.zone.dz2022 ? data.zone.dz2022 : null;

  return (
    <div className="hud-card hud-wealth animate-in slide-in-from-right" role="dialog" aria-label="National wealth">
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="absolute top-4 right-4 p-2 hover:bg-slate-100 rounded-full transition-colors"
      >
        ✕
      </button>
      <h2 className="text-xl font-bold mb-4 text-slate-900">National Wealth</h2>

      {isLoading ? (
        <div className="flex items-center justify-center h-64" aria-busy="true">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      ) : failure ? (
        <div className="p-4 rounded-lg border border-amber-200 bg-amber-50 text-sm">
          <p className="font-semibold text-amber-900">{failureText(failure).title}</p>
          <p className="text-amber-800 mt-1">{failureText(failure).body}</p>
          {failure.reasons && failure.reasons.length > 0 && (
            <ul className="mt-2 text-xs text-amber-700 list-disc pl-4">
              {failure.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      ) : data && w ? (
        <div className="space-y-5">
          <section className="bg-slate-50 p-3 rounded-lg border border-slate-100">
            <p className="text-xs text-slate-500 uppercase font-semibold mb-1">Data zone</p>
            <p className="text-sm font-medium text-slate-700">
              {data.wealth.zone.code} ({data.wealth.zone.vintage}){data.zone.name ? ` · ${data.zone.name}` : ""}
            </p>
            {other && <p className="text-xs text-slate-500">2022 zone: {other.code}</p>}
            {data.zone.zones.some((z) => z.on_boundary) && (
              <p className="text-xs text-amber-700">On a zone boundary: the first matching zone is shown.</p>
            )}
            <p className="text-xs text-slate-400">
              {data.wealth.lat.toFixed(4)}, {data.wealth.lng.toFixed(4)}
            </p>
          </section>

          <ViewPanel views={w.display} />

          <section>
            <h3 className="text-sm font-bold text-slate-900 mb-2">Annual rent by value tier</h3>
            {tiers.length === 0 ? (
              <p className="text-sm text-slate-500 italic">No publishable measured rent here. No total is shown (not £0).</p>
            ) : (
              <div className="space-y-2">
                {tiers.map(([tier, t]) => (
                  <TierRow key={tier} tier={tier} t={t} />
                ))}
                {tiers.length > 1 && (
                  <p className="text-xs text-slate-500">Tiers are different kinds of value and are not added together.</p>
                )}
              </div>
            )}
          </section>

          {w.components.length > 0 && (
            <section>
              <h3 className="text-sm font-bold text-slate-900 mb-2">Components</h3>
              <div className="space-y-2">
                {w.components.map((c, i) => (
                  <ComponentRow key={`${c.layer}-${c.name}-${i}`} c={c} />
                ))}
              </div>
            </section>
          )}

          <section>
            <h3 className="text-sm font-bold text-slate-900 mb-1">Of which (already inside surface rent; not added)</h3>
            <div className="text-xs space-y-1 text-slate-600">
              <div className="flex justify-between">
                <span>Infrastructure share</span>
                <span className="font-mono">{w.attribution.infra_share == null ? "–" : gbp(w.attribution.infra_share)}</span>
              </div>
              <div className="flex justify-between">
                <span>Planning uplift</span>
                <span className="font-mono">
                  {w.attribution.planning_uplift != null
                    ? gbp(w.attribution.planning_uplift)
                    : w.attribution.planning_uplift_flag
                      ? "pending"
                      : "–"}
                </span>
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-sm font-bold text-slate-900 mb-1">Policy view (separate; not measured rent)</h3>
            <div className="flex justify-between text-xs text-slate-600">
              <span>
                Policy rent
                {w.policy.policy_despec_factor != null ? ` (× ${w.policy.policy_despec_factor} de-speculation)` : ""}
              </span>
              <span className="font-mono">{w.policy.policy_rent == null ? "–" : gbp(w.policy.policy_rent)}</span>
            </div>
          </section>

          <TaxScenarioPanel zoneId={data.wealth.zone.code} vintage={data.wealth.zone.vintage} />

          {w.flags.length > 0 && (
            <section>
              <h3 className="text-sm font-bold text-slate-900 mb-1">Notes</h3>
              <ul className="text-xs text-slate-600 list-disc pl-4 space-y-1">
                {w.flags.map((f) => (
                  <li key={f}>{FLAG_LABEL[f] ?? f.replace(/_/g, " ")}</li>
                ))}
              </ul>
            </section>
          )}

          <p className="text-xs text-slate-500">
            Extractive and eco layers are not shown until real data exists. Placeholder figures are never displayed.
          </p>
          {w.context?.access?.status === "ok" && (
            <section aria-label="Access context" className="text-[11px] text-slate-600 space-y-1">
              <h3 className="text-xs font-bold text-slate-700">Access (context only)</h3>
              <p>
                Road distance to nearest large urban centre ({w.context.access.nearest_luc ?? "n/a"}):{" "}
                {w.context.access.road_km_nearest_luc != null ? `${w.context.access.road_km_nearest_luc.toFixed(1)} km` : "n/a"}
                {w.context.access.distance_method === "euclid_x1.3" ? " (1.3 × straight line, no road link)" : ""}
              </p>
              {w.context.access.flags.length > 0 && (
                <p className="text-slate-500">Flags: {w.context.access.flags.join(", ")}</p>
              )}
              <p className="text-slate-400">{w.context.access.note}</p>
            </section>
          )}
          {[...w.attributions, ...(w.context?.access?.attributions ?? [])].length > 0 && (
            <section aria-label="Data credits" className="text-[11px] text-slate-500 space-y-2">
              <h3 className="text-xs font-bold text-slate-700">Data credits</h3>
              {[...w.attributions, ...(w.context?.access?.attributions ?? [])].map((a) => (
                <div key={a.dataset}>
                  <p>{a.attribution}</p>
                  <p className="text-slate-400">Licence: {a.licence}</p>
                </div>
              ))}
            </section>
          )}
          <div className="p-3 bg-blue-50 rounded-lg border border-blue-100">
            <p className="text-xs text-blue-800 leading-relaxed">{w.disclaimer}</p>
          </div>
        </div>
      ) : (
        <div className="text-center py-12 text-slate-400 italic">Click the map to look up a data zone.</div>
      )}
    </div>
  );
}

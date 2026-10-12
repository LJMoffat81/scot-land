"use client";

import { useEffect, useState } from "react";

import { getApiBaseUrl } from "../lib/api";
import type {
  TaxScenarioResponse,
  TaxScenarioZoneResponse,
  Vintage,
} from "../lib/useWealthApi";

const PRESETS = [0, 0.25, 0.5, 0.75, 1] as const;

interface TaxScenarioPanelProps {
  zoneId: string | null;
  vintage: Vintage | null;
}

function gbp(v: number | null | undefined): string {
  if (v == null) return "–";
  return `£${v.toLocaleString("en-GB", { maximumFractionDigits: 0 })}`;
}

function pct(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

async function getJson<T>(path: string): Promise<{ ok: true; data: T } | { ok: false; message: string }> {
  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, { cache: "no-store" });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = body?.detail;
      const message =
        detail && typeof detail === "object" && !Array.isArray(detail)
          ? String(detail.message ?? detail.error ?? response.statusText)
          : response.statusText;
      return { ok: false, message };
    }
    return { ok: true, data: body as T };
  } catch (err) {
    return { ok: false, message: String(err) };
  }
}

/**
 * Tax scenario scaffold on Wealth Engine Surface Rent.
 * Capture rate is a policy illustration only — not AGR and not a tax bill.
 */
export function TaxScenarioPanel({ zoneId, vintage }: TaxScenarioPanelProps) {
  const [rate, setRate] = useState(1);
  const [zonePayload, setZonePayload] = useState<TaxScenarioZoneResponse | null>(null);
  const [national, setNational] = useState<TaxScenarioResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      const vin = vintage ?? 2011;
      const q = `capture_rate=${encodeURIComponent(rate)}&vintage=${vin}`;
      const nationalRes = await getJson<TaxScenarioResponse>(`/georgist/tax-scenario?${q}`);
      if (cancelled) return;
      if (!nationalRes.ok) {
        setNational(null);
        setZonePayload(null);
        setError(nationalRes.message);
        setLoading(false);
        return;
      }
      setNational(nationalRes.data);
      if (!zoneId) {
        setZonePayload(null);
        setLoading(false);
        return;
      }
      const zoneRes = await getJson<TaxScenarioZoneResponse>(
        `/georgist/tax-scenario/zone?zone_id=${encodeURIComponent(zoneId)}&${q}`,
      );
      if (cancelled) return;
      if (!zoneRes.ok) {
        setZonePayload(null);
        setError(zoneRes.message);
      } else {
        setZonePayload(zoneRes.data);
      }
      setLoading(false);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [zoneId, vintage, rate]);

  const topCouncils = (national?.by_council ?? [])
    .slice()
    .sort(
      (a, b) => (b.illustrated_collection_gbp ?? 0) - (a.illustrated_collection_gbp ?? 0),
    )
    .slice(0, 8);

  return (
    <section className="space-y-3" aria-label="Tax scenario tools">
      <div>
        <h3 className="text-sm font-bold text-slate-900">Tax scenario (Surface Rent)</h3>
        <p className="text-xs text-slate-600 mt-1">
          What a land-value capture rate would raise if applied to publishable Wealth Engine
          Surface Rent — by data zone and council. Research estimate only.
        </p>
        <p className="text-xs text-amber-800 mt-1">
          Not AGR residual plot charge. Not the Sandilands national rent pool. Not a tax bill.
        </p>
      </div>

      <div>
        <label className="text-xs font-semibold text-slate-700" htmlFor="tax-capture-rate">
          Capture rate (policy illustration): {pct(rate)}
        </label>
        <input
          id="tax-capture-rate"
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={rate}
          onChange={(e) => setRate(Number(e.target.value))}
          className="w-full mt-1"
        />
        <div className="flex flex-wrap gap-1 mt-1">
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setRate(p)}
              className={`text-xs px-2 py-0.5 border rounded ${
                rate === p ? "bg-slate-800 text-white border-slate-800" : "border-slate-200 text-slate-600"
              }`}
            >
              {pct(p)}
            </button>
          ))}
        </div>
      </div>

      {loading && <p className="text-xs text-slate-500">Loading scenario…</p>}
      {error && (
        <p className="text-xs text-amber-800 border border-amber-200 bg-amber-50 p-2 rounded">
          {error} No figure invented in its place.
        </p>
      )}

      {zonePayload && (
        <div className="space-y-1 text-sm border border-slate-100 rounded p-2 bg-slate-50">
          <p className="text-xs uppercase font-semibold text-slate-500">Selected data zone</p>
          <p className="text-xs text-slate-600">
            {zonePayload.zone.code} · {zonePayload.zone.la_name}
            {zonePayload.zone.price_year != null ? ` · ${zonePayload.zone.price_year} prices` : ""}
          </p>
          <div className="flex justify-between text-xs">
            <span>Measured Surface Rent</span>
            <span className="font-mono">{gbp(zonePayload.zone.measured_rent_gbp)}/yr</span>
          </div>
          <div className="flex justify-between text-xs font-semibold">
            <span>Illustrated collection @ {pct(rate)}</span>
            <span className="font-mono">{gbp(zonePayload.zone.illustrated_collection_gbp)}/yr</span>
          </div>
          {zonePayload.zone.share_of_council_measured_rent != null && (
            <p className="text-xs text-slate-500">
              Share of council measured rent:{" "}
              {(zonePayload.zone.share_of_council_measured_rent * 100).toFixed(1)}%
            </p>
          )}
          <div className="flex justify-between text-xs pt-1 border-t border-slate-200">
            <span>Council illustrated total</span>
            <span className="font-mono">{gbp(zonePayload.council.illustrated_collection_gbp)}/yr</span>
          </div>
          <p className="text-[11px] text-slate-500">{zonePayload.zone.disclaimer}</p>
        </div>
      )}

      {national && (
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-slate-700">
              Scotland (sum of publishable DZ Surface Rent)
              {national.price_year != null ? ` · ${national.price_year}` : ""}
            </span>
            <span className="font-mono font-semibold">
              {gbp(national.national.illustrated_collection_gbp)}/yr
            </span>
          </div>
          <p className="text-[11px] text-slate-500">
            {national.national.zone_count} zones · measured{" "}
            {gbp(national.national.measured_rent_total_gbp)}/yr before capture rate
          </p>
          {topCouncils.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1">Who would pay (by council)</p>
              <ul className="text-xs space-y-1 max-h-40 overflow-y-auto">
                {topCouncils.map((c) => (
                  <li key={c.la_code} className="flex justify-between gap-2">
                    <span className="text-slate-600 truncate">{c.la_name}</span>
                    <span className="font-mono shrink-0">{gbp(c.illustrated_collection_gbp)}/yr</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-[11px] text-slate-500 leading-relaxed">{national.note}</p>
          <p className="text-[11px] text-blue-800">{national.disclaimer}</p>
        </div>
      )}
    </section>
  );
}

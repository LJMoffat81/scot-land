import { useCallback, useState } from "react";

import { getApiBaseUrl } from "./api";

/* ------------------------------------------------------------------ types
 * Mirrors backend/api/wealth_routes.py (public endpoints only). Placeholder
 * (mock) figures never appear in these responses; diagnostics are never served.
 */

export type ValueTier = "market" | "proxy" | "shadow";
export type Quality = "live" | "derived" | "modelled" | "placeholder";
export type PublishLevel = "public_site" | "public_zone" | "internal";
export type PublicationStatus = "ok" | "blocked";
export type ExcludedReason =
  | "placeholder"
  | "blocked"
  | "not_publishable"
  | "no_measured_rent"
  | "unknown_value_tier"
  | "zero_dwellings";

/** Data zone vintage: an integer, 2011 or 2022 ("DZ2011" is rejected with 422 invalid_vintage). */
export type Vintage = 2011 | 2022;

export interface WealthComponent {
  layer: "surface" | "extractive" | "eco";
  name: string | null;
  commons_class: string | null;
  measured_rent_gbp: number | null;
  price_year: number | null; // year the money is priced in (rules section 2)
  evidence_year?: number | null; // raw sales/evidence year
  value_tier: ValueTier | null;
  quality: Quality | null;
  uncertainty_low: number | null;
  uncertainty_high: number | null;
  crosswalk_method: string | null;
  source_id: string | null;
  licence: string | null;
  publish_level: PublishLevel | null;
  publication_status: PublicationStatus;
  in_totals: boolean;
  excluded_reason: ExcludedReason | null;
  withheld: boolean;
  model_filled?: boolean;
  status?: "ok" | "withheld" | "excluded" | "not_applicable";
  /** Valuation quality tags passed through, e.g. plot_bands_borrowed. */
  quality_flags?: string[];
}

export interface TierTotal {
  total_gbp: number | null;
  low_gbp: number | null;
  high_gbp: number | null;
  price_year: number | null;
  components: number;
  flags: string[];
}

export type ViewId = "per_residential_hectare" | "per_dwelling" | "per_resident";
export type ViewStatus = "ok" | "interim_rough" | "denominator_pending" | "withheld" | "not_available" | "not_applicable";

export interface DisplayView {
  status: ViewStatus;
  value: number | null;
  low: number | null;
  high: number | null;
  denominator?: string;
  denominator_value?: number;
  denominator_year?: number | null;
  denominator_source?: string | null;
  flag?: string;
  second_home_share?: number | null;
  second_home_share_status?: "ok" | "denominator_pending";
  vacant_share?: number | null;
  /** per_residential_hectare only: "low" where UPRN-in-parcel coverage < 0.5 or the parcel mask is too big. */
  confidence?: "normal" | "low" | null;
  confidence_reasons?: string[];
}

export interface DisplayViews {
  default: ViewId;
  order: ViewId[];
  unit: string;
  flags: string[]; // e.g. dwellings_count_missing_for_price_year
  views: Record<ViewId, DisplayView>;
}

/** Licence + attribution a public view must show for a dataset it is built from (e.g. EPC rollup). */
export interface DatasetAttribution {
  dataset: string;
  licence: string;
  attribution: string;
  publish_level: string;
  use_restriction?: string;
  source: "manifest"; // the manifest attribution column is the only source
  source_year?: number | null; // optional manifest column (metadata only)
}

/** GIS dz_access context: shown beside the figures, never used in them. Flags verbatim from GIS. */
export interface AccessContext {
  status: "ok" | "not_loaded" | "zone_missing" | "attribution_missing";
  job_access?: number | null;
  log_job_access?: number | null;
  road_km_nearest_luc?: number | null;
  nearest_luc?: string | null;
  distance_method?: string | null; // network | euclid_x1.3
  job_access_method?: string | null; // network | network+euclid_x1.3
  network_component?: string | null;
  flags: string[]; // e.g. luc_distance_euclid_x1.3, nearest_emp_point_gt_5km
  source_year?: number | null;
  attributions: DatasetAttribution[];
  note?: string;
}

export interface WealthPayload {
  components: WealthComponent[];
  totals_by_tier: Partial<Record<ValueTier, TierTotal>>;
  attribution: {
    note: string;
    planning_uplift?: number | null;
    infra_share?: number | null;
    planning_uplift_flag?: string | null;
  };
  policy: { note: string; policy_rent?: number | null; policy_despec_factor?: number | null };
  display: DisplayViews;
  context?: { access?: AccessContext };
  flags: string[];
  attributions: DatasetAttribution[];
  status: string;
  disclaimer: string;
}

export interface ZoneRef {
  code: string;
  vintage: Vintage;
  vintage_source?: string;
}

export interface WealthResponse {
  lat: number;
  lng: number;
  zone_id: string;
  zone: ZoneRef;
  wealth: WealthPayload;
}

export interface DataZoneHit {
  code: string;
  vintage: Vintage;
  name: string | null;
  on_boundary: boolean;
}

export interface DataZoneLookup {
  lat: number;
  lon: number;
  code: string | null;
  name: string | null;
  vintage: Vintage | null;
  zones: DataZoneHit[];
  dz2011: DataZoneHit | null;
  dz2022: DataZoneHit | null;
  source: string;
  vintages_loaded: Vintage[];
}

export interface SurfaceRentZone {
  code: string;
  vintage: Vintage;
  /** not_applicable = zero dwellings (rules v0.7): every figure null, never 0, never summed. */
  status: "ok" | "not_applicable";
  measured_rent: number | null;
  rent_per_residential_ha: number | null;
  rent_per_residential_ha_status: ViewStatus;
  rent_per_residential_ha_confidence: "normal" | "low" | null;
  /** per_dwelling where the residential-area confidence is low. */
  preferred_view: ViewId;
  quality_flags: string[];
  rent_per_dwelling: number | null;
  rent_per_dwelling_status: ViewStatus;
  rent_per_resident: number | null;
  rent_per_resident_status: ViewStatus;
  second_home_share: number | null;
  vacant_share: number | null;
  price_year: number | null;
  evidence_year: number | null;
  denominator_flags: string[];
  [key: string]: unknown;
}

export interface SurfaceRentLayer {
  vintage: Vintage;
  count: number;
  withheld: number;
  withheld_by_reason: Record<string, number>;
  views: { default: ViewId; order: ViewId[]; status_counts: Record<ViewId, Record<string, number>>; note: string };
  data: Record<string, SurfaceRentZone>;
  attributions: DatasetAttribution[];
  method_settings: { depreciation: Record<string, unknown>; [key: string]: unknown };
  zero_dwellings: string[];
}

/** Wealth Engine tax-scenario scaffold: Surface Rent × capture rate (not AGR). */
export interface TaxScenarioCouncilRow {
  la_code: string;
  la_name: string;
  zone_count: number;
  price_year: number | null;
  measured_rent_total_gbp: number | null;
  illustrated_collection_gbp: number | null;
  status: string;
  disclaimer: string;
}

export interface TaxScenarioResponse {
  ok: boolean;
  status: string;
  lens: "surface_rent";
  lens_note: string;
  disclaimer: string;
  capture_rate: number;
  capture_note: string;
  price_year: number | null;
  vintage: Vintage;
  national: {
    zone_count: number;
    measured_rent_total_gbp: number | null;
    illustrated_collection_gbp: number | null;
    price_year?: number | null;
    status?: string;
    disclaimer?: string;
  };
  by_council: TaxScenarioCouncilRow[];
  preset_rates: number[];
  note: string;
  source?: string;
}

export interface TaxScenarioZoneResponse {
  ok: boolean;
  status: string;
  lens: "surface_rent";
  lens_note: string;
  disclaimer: string;
  capture_rate: number;
  capture_note: string;
  zone: {
    code: string;
    vintage: Vintage;
    la_code: string;
    la_name: string;
    price_year: number | null;
    measured_rent_gbp: number | null;
    illustrated_collection_gbp: number | null;
    share_of_council_measured_rent: number | null;
    status: string;
    disclaimer: string;
  };
  council: {
    la_code: string;
    la_name: string;
    zone_count: number | null;
    measured_rent_total_gbp: number | null;
    illustrated_collection_gbp: number | null;
    status: string;
    disclaimer: string;
  };
  note: string;
  vintage: Vintage;
  zone_id: string;
}

/** A failed call, with the API's structured detail when it sent one. */
export interface ApiFailure {
  status: number; // 0 = network error
  error: string; // e.g. invalid_zone_id, wealth_database_unavailable, no_data_zone_at_point, mixed_price_years
  message: string;
  reasons?: string[];
  price_years?: number[];
}

export type Result<T> = { ok: true; data: T } | { ok: false; failure: ApiFailure };

async function getJson<T>(path: string): Promise<Result<T>> {
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, { cache: "no-store" });
  } catch (err) {
    return { ok: false, failure: { status: 0, error: "network_error", message: String(err) } };
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (response.ok) return { ok: true, data: body as T };
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>;
    return {
      ok: false,
      failure: {
        status: response.status,
        error: String(d.error ?? `http_${response.status}`),
        message: String(d.message ?? response.statusText),
        reasons: Array.isArray(d.reasons) ? d.reasons.map(String) : undefined,
        price_years: Array.isArray(d.price_years) ? d.price_years.map(Number) : undefined,
      },
    };
  }
  // FastAPI validation errors (422 list) or plain-string details
  const message = Array.isArray(detail)
    ? detail.map((e) => (e as { msg?: string }).msg ?? "invalid input").join("; ")
    : typeof detail === "string"
      ? detail
      : response.statusText;
  return { ok: false, failure: { status: response.status, error: `http_${response.status}`, message } };
}

/** Primary zone for a lookup: DZ2011 when present (Valuation's surface rent is DZ2011), else DZ2022. */
export function primaryZone(lookup: DataZoneLookup): DataZoneHit | null {
  return lookup.dz2011 ?? lookup.dz2022 ?? null;
}

export function useWealthApi() {
  const [isLoading, setIsLoading] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const fetchDataZoneAt = useCallback(
    (lat: number, lon: number) =>
      getJson<DataZoneLookup>(
        `/layers/context/data-zones/at?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`,
      ),
    [],
  );

  const fetchTotalWealth = useCallback(
    (lat: number, lng: number, zoneId: string, vintage?: Vintage) => {
      const q = new URLSearchParams({ lat: String(lat), lng: String(lng), zone_id: zoneId });
      if (vintage) q.set("vintage", String(vintage));
      return getJson<WealthResponse>(`/georgist/wealth?${q.toString()}`);
    },
    [],
  );

  /** Click flow: point -> data zone (real code) -> wealth. Never sends 'unknown'. */
  const lookupWealthAt = useCallback(
    async (lat: number, lng: number): Promise<Result<{ zone: DataZoneLookup; wealth: WealthResponse }>> => {
      setIsLoading(true);
      setFailure(null);
      try {
        const zone = await fetchDataZoneAt(lat, lng);
        if (!zone.ok) {
          setFailure(zone.failure);
          return zone;
        }
        const primary = primaryZone(zone.data);
        if (!primary) {
          const f = { status: 404, error: "no_data_zone_at_point", message: "No data zone at this point." };
          setFailure(f);
          return { ok: false, failure: f };
        }
        const wealth = await fetchTotalWealth(lat, lng, primary.code, primary.vintage);
        if (!wealth.ok) {
          setFailure(wealth.failure);
          return wealth;
        }
        return { ok: true, data: { zone: zone.data, wealth: wealth.data } };
      } finally {
        setIsLoading(false);
      }
    },
    [fetchDataZoneAt, fetchTotalWealth],
  );

  const fetchSurfaceRentLayer = useCallback(
    (vintage: Vintage = 2011) =>
      getJson<SurfaceRentLayer>(`/layers/georgist/surface-rent?vintage=${vintage}`),
    [],
  );

  const fetchTaxScenario = useCallback(
    (opts: { vintage?: Vintage; captureRate?: number; laCode?: string } = {}) => {
      const q = new URLSearchParams({
        vintage: String(opts.vintage ?? 2011),
        capture_rate: String(opts.captureRate ?? 1),
      });
      if (opts.laCode) q.set("la_code", opts.laCode);
      return getJson<TaxScenarioResponse>(`/georgist/tax-scenario?${q.toString()}`);
    },
    [],
  );

  const fetchTaxScenarioZone = useCallback(
    (zoneId: string, opts: { vintage?: Vintage; captureRate?: number } = {}) => {
      const q = new URLSearchParams({
        zone_id: zoneId,
        capture_rate: String(opts.captureRate ?? 1),
      });
      if (opts.vintage) q.set("vintage", String(opts.vintage));
      return getJson<TaxScenarioZoneResponse>(`/georgist/tax-scenario/zone?${q.toString()}`);
    },
    [],
  );

  // No resource/eco fetchers: today those layers hold only mock data, which the
  // public API does not serve (rules v0.4 section 2). Developers use /internal/...
  return {
    isLoading,
    failure,
    fetchDataZoneAt,
    fetchTotalWealth,
    lookupWealthAt,
    fetchSurfaceRentLayer,
    fetchTaxScenario,
    fetchTaxScenarioZone,
  };
}

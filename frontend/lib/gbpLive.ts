/**
 * GBP-LIVE — public £ surface rent display behind ONE flag (default OFF).
 * Backend source of truth: data/config/gbp_live.yaml via GET /platform/gbp-live.
 *
 * GBP-LIVE-V1c: residential surface rent ÷ residential_land_ha; on-screen unit
 * label exactly "£ per square metre of land, per year"; 3 significant figures;
 * values below £0.01 as "<£0.01"; never "£0.00"; unavailable/clamped/bad area
 * → "estimate unavailable". Keep this module free of top-level ./api imports so
 * Node unit scripts can load the formatters without resolving the Next fetch stack.
 */

export const GBP_LIVE_EARLY_BANNER =
  "Early estimates; ranges are wide and will change.";

/** GBP-LIVE-V1c — replaces "Under review"; never show £0. */
export const GBP_LIVE_ESTIMATE_UNAVAILABLE = "estimate unavailable";

/** @deprecated Use GBP_LIVE_ESTIMATE_UNAVAILABLE (V1c). */
export const GBP_LIVE_UNDER_REVIEW = GBP_LIVE_ESTIMATE_UNAVAILABLE;

/** Place-card rent-rate line (signed off; never the banned word "yield"). */
export const GBP_LIVE_RENT_RATE_CARD =
  "Yearly rent: up to 4.5% of the land's value";

/** How it works rent-rate line (signed off; never the banned word "yield"). */
export const GBP_LIVE_RENT_RATE_HOW_IT_WORKS =
  "We turn land value into a yearly rent of up to 4.5% of that value.";

/** Short unit suffix on every £ amount string behind the flag. */
export const GBP_LIVE_UNIT = "per m²";

/**
 * On-screen unit label (GBP-LIVE-V1c) — must match exactly, including £.
 * Backend API `unit_wording` omits the £ glyph; always prefer this constant
 * for visitor-facing copy.
 */
export const GBP_LIVE_UNIT_WORDING =
  "£ per square metre of land, per year";

/** Central figure label (spec: "most likely" central). */
export const GBP_LIVE_CENTRAL_LABEL = "most likely";

/** Below this £/m²/year rate, display "<£0.01" (never "£0.00"). */
export const GBP_LIVE_MIN_DISPLAY_GBP = 0.01;

export type GbpLiveSettings = {
  enabled: boolean;
  banner?: string | null;
  rent_rate_wording?: string | null;
  unit?: string | null;
  unit_wording?: string | null;
};

export type SurfaceRentDisplayState = "ok" | "under_review" | "hidden";

export type SurfaceRentDisplay = {
  state: SurfaceRentDisplayState | string;
  label?: string | null;
  estimate_label?: string | null;
  estimate_label_key?: string | null;
  low?: number | null;
  central?: number | null;
  high?: number | null;
  rent_rate_wording?: string | null;
  unit?: string | null;
  unit_wording?: string | null;
  central_label?: string | null;
  grain?: string | null;
};

/** Format a whole-pound amount with a sterling prefix (runtime only). */
export function formatGbp(value: number): string {
  const n = Number.isFinite(value) ? Math.round(value) : 0;
  return `\u00a3${n.toLocaleString("en-GB", { maximumFractionDigits: 0 })}`;
}

/**
 * Format a £/m² rate body with 3 significant figures.
 * Non-finite / zero / negative (incl. -0) → "estimate unavailable" (fail closed).
 * Finite values below £0.01 → "<£0.01". Never returns "£0.00".
 */
export function formatGbpPerM2Amount(value: number | null | undefined): string {
  // Missing values fail closed before Number() (Number(null)===0 would mislead).
  if (value == null) {
    return GBP_LIVE_ESTIMATE_UNAVAILABLE;
  }
  const n = typeof value === "number" ? value : Number(value);
  // NaN / Infinity / zero / negative (incl. -0): unavailable — not a tiny £ rate.
  if (!Number.isFinite(n) || n <= 0) {
    return GBP_LIVE_ESTIMATE_UNAVAILABLE;
  }
  if (n < GBP_LIVE_MIN_DISPLAY_GBP) {
    return `<\u00a3${GBP_LIVE_MIN_DISPLAY_GBP.toFixed(2)}`;
  }
  let body = n.toPrecision(3);
  if (/e/i.test(body)) {
    body = Number(n.toPrecision(3)).toLocaleString("en-GB", {
      maximumSignificantDigits: 3,
      useGrouping: false,
    });
  }
  // Guard: never emit the banned £0.00 form.
  if (body === "0.00" || body === "0.000" || Number(body) === 0) {
    return `<\u00a3${GBP_LIVE_MIN_DISPLAY_GBP.toFixed(2)}`;
  }
  return `\u00a3${body}`;
}

/** Format £ per m² — every £ string includes the unit; 3 sf / <£0.01. */
export function formatGbpPerM2(value: number | null | undefined): string {
  const amount = formatGbpPerM2Amount(value);
  if (amount === GBP_LIVE_ESTIMATE_UNAVAILABLE) return amount;
  return `${amount} ${GBP_LIVE_UNIT}`;
}

/** Central figure with low–high range beside it (legacy whole-pound helper). */
export function formatGbpCentralWithRange(
  low: number,
  central: number,
  high: number,
): { central: string; range: string } {
  return {
    central: formatGbp(central),
    range: `${formatGbp(low)}\u2013${formatGbp(high)}`,
  };
}

/**
 * GBP-LIVE-V1d: central + range as £ per m² (3 sf; <£0.01 floor).
 * Each returned string that carries £ also carries "per m²".
 * Invalid / zero / out-of-order inputs fail closed to "estimate unavailable" (no £).
 */
export function formatGbpCentralWithRangePerM2(
  low: number | null | undefined,
  central: number | null | undefined,
  high: number | null | undefined,
): { central: string; range: string } {
  const lo = formatGbpPerM2Amount(low);
  const mid = formatGbpPerM2(central);
  const hi = formatGbpPerM2Amount(high);
  if (
    lo === GBP_LIVE_ESTIMATE_UNAVAILABLE ||
    mid === GBP_LIVE_ESTIMATE_UNAVAILABLE ||
    hi === GBP_LIVE_ESTIMATE_UNAVAILABLE
  ) {
    return {
      central: GBP_LIVE_ESTIMATE_UNAVAILABLE,
      range: GBP_LIVE_ESTIMATE_UNAVAILABLE,
    };
  }
  // Out-of-order low/central/high → unavailable (no £).
  if (
    typeof low === "number" &&
    typeof central === "number" &&
    typeof high === "number" &&
    (low > central || central > high)
  ) {
    return {
      central: GBP_LIVE_ESTIMATE_UNAVAILABLE,
      range: GBP_LIVE_ESTIMATE_UNAVAILABLE,
    };
  }
  return {
    central: mid,
    // Single unit suffix on the range so the string still contains "per m²".
    range: `${lo}\u2013${hi} ${GBP_LIVE_UNIT}`,
  };
}


/**
 * GBP-LIVE-V1d place-card answer range: per-m² low–high with 3 sf.
 * Takes low/central/high; returns "estimate unavailable" if any is unavailable
 * or if low > central or central > high. Values below £0.01 render as "<£0.01".
 * Never "£0.00". No single-point £, no total.
 * Exported from placeCard.ts for callers; lives here so Node unit tests can load it.
 */
export function formatPlaceCardGbpRange(
  low: number | null | undefined,
  central: number | null | undefined,
  high: number | null | undefined,
): string {
  const lo = formatGbpPerM2Amount(low);
  const mid = formatGbpPerM2Amount(central);
  const hi = formatGbpPerM2Amount(high);
  if (
    lo === GBP_LIVE_ESTIMATE_UNAVAILABLE ||
    mid === GBP_LIVE_ESTIMATE_UNAVAILABLE ||
    hi === GBP_LIVE_ESTIMATE_UNAVAILABLE
  ) {
    return GBP_LIVE_ESTIMATE_UNAVAILABLE;
  }
  // Out-of-order low/central/high → unavailable (no £).
  if (
    typeof low === "number" &&
    typeof central === "number" &&
    typeof high === "number" &&
    (low > central || central > high)
  ) {
    return GBP_LIVE_ESTIMATE_UNAVAILABLE;
  }
  return `${lo} to ${hi} ${GBP_LIVE_UNIT}`;
}

export function gbpLiveFromCard(card: {
  gbp_live?: { enabled?: boolean } | null;
} | null | undefined): boolean {
  return Boolean(card?.gbp_live?.enabled);
}

let _cached: GbpLiveSettings | null = null;
let _inflight: Promise<GbpLiveSettings> | null = null;

export function clearGbpLiveSettingsCache(): void {
  _cached = null;
  _inflight = null;
}

/**
 * Fetch public GBP-LIVE settings (cached).
 * Uses same-origin ``/api/gbp-live`` which always returns HTTP 200
 * (``enabled: false`` when the backend flag is off or unreachable) so e2e
 * console/404 traps never see a failed ``/backend/platform/gbp-live`` probe.
 */
export async function fetchGbpLiveSettings(): Promise<GbpLiveSettings> {
  if (_cached) return _cached;
  if (_inflight) return _inflight;
  _inflight = fetch("/api/gbp-live", {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  })
    .then(async (res) => {
      if (!res.ok) {
        return { enabled: false } satisfies GbpLiveSettings;
      }
      const body = (await res.json()) as GbpLiveSettings;
      return {
        enabled: Boolean(body?.enabled),
        banner: body?.banner ?? null,
        rent_rate_wording: body?.rent_rate_wording ?? null,
        unit: body?.unit ?? null,
        unit_wording: body?.unit_wording ?? null,
      } satisfies GbpLiveSettings;
    })
    .catch(() => ({ enabled: false }) satisfies GbpLiveSettings)
    .then((settings) => {
      _cached = settings;
      return settings;
    })
    .finally(() => {
      _inflight = null;
    });
  return _inflight;
}

/**
 * Illustrative Data Zone surface-rent legend stops (£ per m² / year) when the flag is on.
 * Labels are ranges only — never a national total.
 */
export const SURFACE_RENT_LEGEND_STOPS: Array<[number, string]> = [
  [0.5, "#f7fcf5"],
  [1, "#c7e9c0"],
  [2, "#74c476"],
  [5, "#238b45"],
  [10, "#00441b"],
];

export const SURFACE_RENT_LEGEND_TITLE =
  "Surface land rent — £ per square metre of land, per year (Data Zone)";

export const SURFACE_RENT_LEGEND_BLURB =
  "Early estimates for land under homes, shown as £ per square metre of land, per year. Ranges are wide and will change.";

export const SURFACE_RENT_LEGEND_SOURCE =
  "Research estimate — Data Zone only; parts are not added into a total. Figures are £ per square metre of land, per year.";

/**
 * GBP-LIVE — public £ surface rent display behind ONE flag (default OFF).
 * Backend source of truth: data/config/gbp_live.yaml via GET /platform/gbp-live.
 *
 * GBP-LIVE-V1b: every £ behind the flag is per m² of land a year (range +
 * "most likely" central + estimate label). Keep this module free of top-level
 * ./api imports so Node unit scripts can load the formatters without resolving
 * the Next fetch stack.
 */

export const GBP_LIVE_EARLY_BANNER =
  "Early estimates; ranges are wide and will change.";

export const GBP_LIVE_UNDER_REVIEW = "Under review";

/** Place-card rent-rate line (signed off; never the banned word "yield"). */
export const GBP_LIVE_RENT_RATE_CARD =
  "Yearly rent: up to 4.5% of the land's value";

/** How it works rent-rate line (signed off; never the banned word "yield"). */
export const GBP_LIVE_RENT_RATE_HOW_IT_WORKS =
  "We turn land value into a yearly rent of up to 4.5% of that value.";

/** GBP-LIVE-V1b unit suffix — every £ string behind the flag includes this. */
export const GBP_LIVE_UNIT = "per m²";

/** Full unit wording for place card / legend / How it works. */
export const GBP_LIVE_UNIT_WORDING = "per m² of land a year";

/** Central figure label (spec: "most likely" central). */
export const GBP_LIVE_CENTRAL_LABEL = "most likely";

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

/** Format £ per m² (two decimal places) — every £ string includes the unit. */
export function formatGbpPerM2(value: number): string {
  const n = Number.isFinite(value) ? value : 0;
  const formatted = n.toLocaleString("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `\u00a3${formatted} ${GBP_LIVE_UNIT}`;
}

function formatGbpAmountPerM2(value: number): string {
  const n = Number.isFinite(value) ? value : 0;
  return `\u00a3${n.toLocaleString("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
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
 * GBP-LIVE-V1b: central + range as £ per m².
 * Each returned string that carries £ also carries "per m²".
 */
export function formatGbpCentralWithRangePerM2(
  low: number,
  central: number,
  high: number,
): { central: string; range: string } {
  return {
    central: formatGbpPerM2(central),
    // Single unit suffix on the range so the string still contains "per m²".
    range: `${formatGbpAmountPerM2(low)}\u2013${formatGbpAmountPerM2(high)} ${GBP_LIVE_UNIT}`,
  };
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
  "Surface land rent — per m² a year (Data Zone)";

export const SURFACE_RENT_LEGEND_BLURB =
  "Early estimates for land under homes, shown per m² of land a year. Ranges are wide and will change.";

export const SURFACE_RENT_LEGEND_SOURCE =
  "Research estimate — Data Zone only; parts are not added into a total. Figures are per m².";

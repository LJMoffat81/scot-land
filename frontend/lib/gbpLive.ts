/**
 * GBP-LIVE-V1 — public £ surface rent display behind ONE flag (default OFF).
 * Backend source of truth: data/config/gbp_live.yaml via GET /platform/gbp-live.
 *
 * Keep this module free of top-level ./api imports so Node unit scripts can load
 * the formatters without resolving the Next fetch stack.
 */

export const GBP_LIVE_EARLY_BANNER =
  "Early estimates; ranges are wide and will change.";

export const GBP_LIVE_UNDER_REVIEW = "Under review";

/** Yield visitor wording — always "up to" (high of signed-off band). */
export const GBP_LIVE_YIELD_UP_TO = "up to 4.5%";

export type GbpLiveSettings = {
  enabled: boolean;
  banner?: string | null;
  yield_wording?: string | null;
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
  yield_wording?: string | null;
  grain?: string | null;
};

/** Format a whole-pound amount with a sterling prefix (runtime only). */
export function formatGbp(value: number): string {
  const n = Number.isFinite(value) ? Math.round(value) : 0;
  return `\u00a3${n.toLocaleString("en-GB", { maximumFractionDigits: 0 })}`;
}

/** Central figure with low–high range beside it. */
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

/** Fetch public GBP-LIVE settings (cached). Default OFF on failure. */
export async function fetchGbpLiveSettings(): Promise<GbpLiveSettings> {
  if (_cached) return _cached;
  if (_inflight) return _inflight;
  _inflight = import("./api")
    .then(({ apiJson }) => apiJson<GbpLiveSettings>("/platform/gbp-live"))
    .then((body) => {
      const settings: GbpLiveSettings = {
        enabled: Boolean(body?.enabled),
        banner: body?.banner ?? null,
        yield_wording: body?.yield_wording ?? null,
      };
      _cached = settings;
      return settings;
    })
    .catch(() => {
      const fallback: GbpLiveSettings = { enabled: false };
      _cached = fallback;
      return fallback;
    })
    .finally(() => {
      _inflight = null;
    });
  return _inflight;
}

/**
 * Illustrative Data Zone surface-rent legend stops (£ / year) for when the flag is on.
 * Labels are ranges only — never a national total.
 */
export const SURFACE_RENT_LEGEND_STOPS: Array<[number, string]> = [
  [5_000, "#f7fcf5"],
  [15_000, "#c7e9c0"],
  [40_000, "#74c476"],
  [80_000, "#238b45"],
  [150_000, "#00441b"],
];

export const SURFACE_RENT_LEGEND_TITLE =
  "Surface land rent — per year (Data Zone)";

export const SURFACE_RENT_LEGEND_BLURB =
  "Early estimates for land under homes. Ranges are wide and will change.";

export const SURFACE_RENT_LEGEND_SOURCE =
  "Research estimate — Data Zone only; parts are not added into a total.";

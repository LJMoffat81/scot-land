/**
 * Place view per-hectare stack (place_hectare_stack_v1).
 * Mirrors GET /api/place-stack.json — placeholders only, no modelled AGR £.
 */

import { apiJson } from "./api";

export type PlaceStackTag =
  | "market"
  | "proxy"
  | "shadow"
  | "market_or_proxy"
  | "reported"
  | "already_included"
  | "nested";

export type PlaceStackRowStatus =
  | "counted"
  | "partial"
  | "not_yet"
  | "excluded"
  | string;

export type PlaceStackRow = {
  id: string;
  label: string;
  tag: PlaceStackTag | string;
  status: PlaceStackRowStatus;
  status_note: string;
  parent_id: string | null;
  nested: boolean;
  in_total: boolean;
  stack: "headline" | "shadow" | "outside" | string;
  amount_placeholder: string;
  /** Always null on public payloads while figures are unpublished. */
  amount_gbp_per_ha: number | null;
  outside_scottish_total?: boolean;
};

export type PlaceStackSection = {
  label: string;
  unit?: string;
  rows: PlaceStackRow[];
  sum_row_ids: string[];
  total_placeholder: string;
  total_note: string;
};

export type PlaceStackOutside = {
  label: string;
  rows: PlaceStackRow[];
  benchmarks: Array<{ id: string; label: string; note: string }>;
  benchmark_label: string;
  note: string;
};

export type PlaceStackConstraint = {
  id: string;
  label: string;
  rule: string;
};

export type PlaceHectareStackPayload = {
  contract: "place_hectare_stack_v1" | string;
  published: boolean;
  reason?: string;
  grain?: string;
  zone: {
    code: string;
    name?: string | null;
    publication_status?: string;
  };
  note?: string;
  publication_note?: string;
  headline: PlaceStackSection | null;
  shadow: PlaceStackSection | null;
  outside: PlaceStackOutside | null;
  constraints: PlaceStackConstraint[] | null;
  checks_url?: string;
  stamp?: { commit?: string };
};

/** Demo fixture — placeholders only; nested 1a + separate shadow. */
export const PLACE_STACK_FIXTURE: PlaceHectareStackPayload = {
  contract: "place_hectare_stack_v1",
  published: true,
  grain: "Figures are being checked and aren't published yet.",
  zone: {
    code: "S01014567",
    name: "City Centre South",
    publication_status: "ok",
  },
  publication_note:
    "Rent for each hectare. Figures are being checked and aren't published yet. Planning permission value is shown inside land, not added again. Services of nature are shown on their own and never added in. Oil and gas are offshore and kept out of Scotland's land total.",
  headline: {
    label: "Scottish totals (Market and Modelled)",
    unit: "per hectare per year",
    sum_row_ids: ["1", "2", "3", "4", "5", "6"],
    total_placeholder: "—",
    total_note:
      "Visually stacked rows that add to this total: 1, 2, 3, 4, 5, 6. Planning uplift excluded from the sum.",
    rows: [
      {
        id: "1",
        label: "Land",
        tag: "market_or_proxy",
        status: "not_yet",
        status_note:
          "Best permitted use. Figures are being checked and aren't published yet.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "headline",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "1a",
        label: "Planning uplift",
        tag: "already_included",
        status: "not_yet",
        status_note:
          "Value from planning permission. Part of the land figure, not added again.",
        parent_id: "1",
        nested: true,
        in_total: false,
        stack: "headline",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "2",
        label: "Minerals and quarries",
        tag: "proxy",
        status: "not_yet",
        status_note:
          "The royalty paid for each tonne taken from the ground.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "headline",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "3",
        label: "Wind and hydro sites on land",
        tag: "proxy",
        status: "partial",
        status_note:
          "The extra rent a wind or hydro site earns over ordinary land rent.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "headline",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "4",
        label: "Seabed and shore",
        tag: "market",
        status: "not_yet",
        status_note:
          "Rent Crown Estate Scotland charges for offshore wind, cables, moorings and the shore.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "headline",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "5",
        label: "Fish farm sites",
        tag: "proxy",
        status: "not_yet",
        status_note: "Total minus the seabed lease paid to Crown Estate Scotland.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "headline",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "6",
        label: "Fishing quota",
        tag: "proxy",
        status: "not_yet",
        status_note: "Market if lease prices, else modelled.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "headline",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
    ],
  },
  shadow: {
    label: "Services of nature (estimates, shown on their own and never added in)",
    unit: "per hectare per year",
    sum_row_ids: ["7", "8", "10"],
    total_placeholder: "—",
    total_note:
      "Estimate stack total is separate from the Scottish totals. Totals per chip only, never across chips or price years.",
    rows: [
      {
        id: "7",
        label: "Water scarcity",
        tag: "shadow",
        status: "not_yet",
        status_note:
          "Value with no market price — not yet published.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "shadow",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "8",
        label: "Carbon held in peat and soil",
        tag: "shadow",
        status: "not_yet",
        status_note:
          "Carbon with no market price. Timber and carbon credits are counted with the land.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "shadow",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "10",
        label: "Other services of nature, such as flood control",
        tag: "shadow",
        status: "not_yet",
        status_note: "Estimate. Not worked out yet.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "shadow",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
    ],
  },
  outside: {
    label: "Outside Scottish total",
    note:
      "Oil and gas (row 9) — offshore, outside the Scottish land total. Benchmarks are shown alongside the breakdown and are never inputs.",
    benchmark_label: "benchmark only, not inputs",
    rows: [
      {
        id: "9",
        label: "Oil & gas",
        tag: "reported",
        status: "excluded",
        status_note:
          "Offshore, outside the Scottish land total.",
        parent_id: null,
        nested: false,
        in_total: false,
        stack: "outside",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
        outside_scottish_total: true,
      },
    ],
    benchmarks: [
      {
        id: "spectrum_airspace",
        label: "Radio spectrum and airspace",
        note: "benchmark only, not inputs",
      },
      {
        id: "wightman",
        label: "Andy Wightman's land estimates",
        note: "benchmark only, not inputs",
      },
    ],
  },
  constraints: [
    {
      id: "designations",
      label: "Designations",
      rule: "Constraint: changes best use, adds no value",
    },
    { id: "flood", label: "Flood", rule: "Constraint: changes best use, adds no value" },
    {
      id: "crofting",
      label: "Crofting / common grazings",
      rule: "Constraint: changes best use, adds no value",
    },
    {
      id: "lca",
      label: "Land Capability for Agriculture (LCA)",
      rule: "Constraint: changes best use, adds no value",
    },
  ],
  checks_url: "/data",
};

export const PLACE_STACK_BLOCKED_FIXTURE: PlaceHectareStackPayload = {
  contract: "place_hectare_stack_v1",
  published: false,
  reason: "blocked",
  grain: "Figures are being checked and aren't published yet.",
  zone: {
    code: "S01008680",
    name: null,
    publication_status: "blocked",
  },
  note:
    "Nothing published for blocked zones (publication_status=blocked — ceiling breach / hold rules).",
  publication_note:
    "Blocked zone — no per-hectare stack published.",
  headline: null,
  shadow: null,
  outside: null,
  constraints: null,
};

export type FetchPlaceStackArgs = {
  zone?: string | null;
  lat?: number | null;
  lng?: number | null;
};

export function fetchPlaceStack({
  zone,
  lat,
  lng,
}: FetchPlaceStackArgs): Promise<PlaceHectareStackPayload> {
  const params = new URLSearchParams();
  if (zone) params.set("zone", zone);
  if (lat != null) params.set("lat", String(lat));
  if (lng != null) params.set("lng", String(lng));
  return apiJson<PlaceHectareStackPayload>(
    `/api/place-stack.json?${params.toString()}`,
  );
}

/** Guard: drop any accidental numeric AGR fields before render. */
export function sanitizePlaceStack(
  payload: PlaceHectareStackPayload,
): PlaceHectareStackPayload {
  const scrubRow = (row: PlaceStackRow): PlaceStackRow => ({
    ...row,
    amount_gbp_per_ha: null,
    amount_placeholder: row.amount_placeholder || "—",
  });
  const scrubSection = (
    section: PlaceStackSection | null,
  ): PlaceStackSection | null => {
    if (!section) return null;
    return {
      ...section,
      total_placeholder: section.total_placeholder || "—",
      rows: section.rows.map(scrubRow),
    };
  };
  return {
    ...payload,
    headline: scrubSection(payload.headline),
    shadow: scrubSection(payload.shadow),
    outside: payload.outside
      ? {
          ...payload.outside,
          rows: payload.outside.rows.map(scrubRow),
        }
      : null,
  };
}

export function tagLabel(tag: string): string {
  switch (tag) {
    case "market":
      return "Market";
    case "proxy":
      return "Modelled";
    case "shadow":
      return "Estimate";
    case "market_or_proxy":
      return "Market / Modelled";
    case "reported":
      return "outside";
    case "already_included":
      return "already included";
    case "nested":
      return "already included";
    default: {
      const _exhaustive: string = tag;
      return _exhaustive;
    }
  }
}

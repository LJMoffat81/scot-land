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
    "Per-hectare stack. Figures are being checked and aren't published yet. Planning uplift sits under land. Services of nature stay separate from market and proxy rows. Oil and gas sit outside the Scottish land total.",
  headline: {
    label: "Scottish totals (market and proxy)",
    unit: "per hectare per year",
    sum_row_ids: ["1", "2", "3", "4"],
    total_placeholder: "—",
    total_note:
      "Visually stacked rows that add to this total: 1, 2, 3, 4. Planning uplift excluded from the sum.",
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
          "Planning uplift: an 'of which' figure inside the land part, never added again",
        parent_id: "1",
        nested: true,
        in_total: false,
        stack: "headline",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "2",
        label: "Mineral rent",
        tag: "proxy",
        status: "not_yet",
        status_note:
          "Royalty/tonne, below ground. Stated difference only (C-hectare).",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "headline",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "3",
        label: "Onshore wind + hydro resource rent",
        tag: "proxy",
        status: "partial",
        status_note:
          "Site rent minus footprint surface rent. Inventory layers may paint.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "headline",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "4",
        label: "Seabed & foreshore",
        tag: "market",
        status: "not_yet",
        status_note: "CES offshore wind, cables, moorings, foreshore.",
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
    label: "Services of nature (separate — never summed into Scottish totals)",
    unit: "per hectare per year",
    sum_row_ids: ["5", "6", "7", "8", "10"],
    total_placeholder: "—",
    total_note:
      "Estimate stack total is separate from the Scottish totals. Totals per chip only, never across chips or price years.",
    rows: [
      {
        id: "5",
        label: "Aquaculture licence rent",
        tag: "shadow",
        status: "not_yet",
        status_note: "Estimate — total minus CES seabed paid. Separate stack.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "shadow",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "6",
        label: "Fisheries quota",
        tag: "shadow",
        status: "not_yet",
        status_note:
          "Market if lease prices, else Estimate (default: Estimate stack).",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "shadow",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
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
        label: "Unpriced peat/soil carbon",
        tag: "shadow",
        status: "not_yet",
        status_note: "Only unpriced carbon; timber/credits stay in row 1.",
        parent_id: null,
        nested: false,
        in_total: true,
        stack: "shadow",
        amount_placeholder: "—",
        amount_gbp_per_ha: null,
      },
      {
        id: "10",
        label: "Ecosystem services",
        tag: "shadow",
        status: "not_yet",
        status_note: "Estimate, later.",
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
        label: "Spectrum / airspace",
        note: "benchmark only, not inputs",
      },
      {
        id: "wightman",
        label: "Wightman",
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
      return "market";
    case "proxy":
      return "proxy";
    case "shadow":
      return "Estimate";
    case "market_or_proxy":
      return "market / proxy";
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

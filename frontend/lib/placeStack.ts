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
  /** Always null on public payloads until ECONOMIC_RULES approve £. */
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
  grain: "zone-level only; never plots; nothing published for blocked zones",
  zone: {
    code: "S01010264",
    name: "City Centre South",
    publication_status: "ok",
  },
  publication_note:
    "Per-hectare stack (Natural capital ledger). Public AGR £ withheld until ECONOMIC_RULES / calibration. Placeholders are not £0. Nested 1a is indented and never added. Shadow total is separate and never summed into the headline. Oil & gas and benchmarks sit outside both.",
  headline: {
    label: "Headline (market + proxy)",
    unit: "£/ha/year",
    sum_row_ids: ["1", "2", "3", "4"],
    total_placeholder: "—",
    total_note:
      "Visually stacked rows that add to this total: 1, 2, 3, 4. Nested 1a excluded from the sum.",
    rows: [
      {
        id: "1",
        label: "Surface site rent",
        tag: "market_or_proxy",
        status: "not_yet",
        status_note:
          "Best permitted use. Public £ withheld until ECONOMIC_RULES / calibration.",
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
        tag: "nested",
        status: "not_yet",
        status_note: "Nested in row 1 — never added as a sibling total.",
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
          "Site rent minus footprint surface rent. Inventory may paint; £ withheld.",
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
    label: "Shadow (separate — never summed into headline)",
    unit: "£/ha/year",
    sum_row_ids: ["5", "6", "7", "8", "10"],
    total_placeholder: "—",
    total_note:
      "Shadow stack total is separate from the headline (C-totals). Never added into market+proxy.",
    rows: [
      {
        id: "5",
        label: "Aquaculture licence rent",
        tag: "shadow",
        status: "not_yet",
        status_note: "Shadow — total minus CES seabed paid. Separate stack.",
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
          "Market if lease prices, else shadow (default: shadow stack).",
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
          "Shadow, ~0 when published. Not shown as £0 while not yet.",
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
        status_note: "Shadow, later.",
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
      "Oil & gas (row 9) is reported UK-reserved and sits outside headline and shadow Scottish totals. Benchmarks are beside the ledger and never inputs.",
    benchmark_label: "benchmark only, not inputs",
    rows: [
      {
        id: "9",
        label: "Oil & gas",
        tag: "reported",
        status: "excluded",
        status_note:
          "UK-reserved — outside Scottish total (headline and shadow).",
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
      rule: "£0, changes best use",
    },
    { id: "flood", label: "Flood", rule: "£0, changes best use" },
    {
      id: "crofting",
      label: "Crofting / common grazings",
      rule: "£0, changes best use",
    },
    {
      id: "lca",
      label: "Land Capability for Agriculture (LCA)",
      rule: "£0, changes best use",
    },
  ],
  checks_url: "/data",
};

export const PLACE_STACK_BLOCKED_FIXTURE: PlaceHectareStackPayload = {
  contract: "place_hectare_stack_v1",
  published: false,
  reason: "blocked",
  grain: "zone-level only; never plots; nothing published for blocked zones",
  zone: {
    code: "S01008680",
    name: null,
    publication_status: "blocked",
  },
  note:
    "Nothing published for blocked zones (publication_status=blocked — ceiling breach / hold rules).",
  publication_note:
    "Blocked zone — no per-hectare stack and no modelled AGR £.",
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
      return "shadow";
    case "market_or_proxy":
      return "market / proxy";
    case "reported":
      return "reported";
    case "nested":
      return "nested";
    default: {
      const _exhaustive: string = tag;
      return _exhaustive;
    }
  }
}

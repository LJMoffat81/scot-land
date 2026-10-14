/**
 * Natural capital ledger contracts:
 * - GET /api/ledger.json — rows 1–10 (+1a), checks, excluded, benchmarks (Data / API)
 * - GET /ledger — ROWS 1–10 + nested 1a + Constraints (map HUD panel)
 *
 * Public payload carries no rent figures; amounts stay placeholders.
 */

import { ApiError, apiJson, visitorFacingError } from "@/lib/api";

/* ---- Data section catalog (GET /api/ledger.json) ---- */

export type LedgerCheckResult = "pass" | "fail" | "pending";

export type LedgerTestLogEntry = {
  id: string;
  status: LedgerCheckResult | string;
  detail: string;
};

export type LedgerCheck = {
  id: string;
  meaning: string;
  result: LedgerCheckResult;
  run_hash: string;
  test_log: LedgerTestLogEntry[];
};

export type LedgerExcluded = {
  id: string;
  label: string;
  reason: string;
};

export type LedgerBenchmark = {
  id: string;
  label: string;
  note: string;
};

/** Sceptic row from GET /api/ledger.json (not the HUD LedgerRow shape). */
export type LedgerCatalogRow = {
  id: string;
  label: string;
  tag: "market" | "proxy" | "shadow" | "reported";
  status: "counted" | "partial" | "not_yet" | "excluded";
  source: string;
  licence: string;
  licence_url?: string | null;
  vintage: string | number | null;
  coverage_pct: number | null;
  /** Range band — null when status is not_yet (never shown as £0). */
  range: {
    low_gbp_per_ha_yr?: number | null;
    high_gbp_per_ha_yr?: number | null;
    unit?: string;
  } | null;
  stack: "headline" | "shadow" | "outside";
  note?: string;
  nested_under?: string;
  never_added?: boolean;
  outside_scottish_total?: boolean;
};

export type LedgerTotals = {
  headline: {
    tiers: string[];
    row_ids: string[];
    status: string;
    range: null | { low?: number | null; high?: number | null };
    note?: string;
  };
  shadow: {
    row_ids: string[];
    status: string;
    range: null | { low?: number | null; high?: number | null };
    never_summed_into_headline: boolean;
    note?: string;
  };
  outside: {
    oil_gas: {
      row_ids: string[];
      status: string;
      range: null | { low?: number | null; high?: number | null };
      note?: string;
    };
    benchmarks: string;
  };
};

export type LedgerCatalog = {
  version: number;
  kind: string;
  brief?: string;
  spec?: string;
  grain?: string;
  rows?: LedgerCatalogRow[];
  totals?: LedgerTotals | null;
  checks: LedgerCheck[];
  excluded: LedgerExcluded[];
  benchmarks: LedgerBenchmark[];
  benchmark_label: string;
  economic_rules?: {
    approved: boolean;
    document?: string;
    modelled_agr_gbp_public: boolean;
    note?: string;
  };
  published?: boolean;
  zone?: {
    code: string;
    vintage: number;
    publication_status: string;
    publish_level?: string | null;
    quality?: string | null;
  };
  reason?: string;
  stamp?: { commit?: string };
};

export const LEDGER_CHECK_ORDER = [
  "C-hectare",
  "C-turbine",
  "C-aqua",
  "C-mineral",
  "C-forest",
  "C-planning",
  "C-overlay",
  "C-overlap",
  "C-totals",
  "C-cap",
] as const;

export const LEDGER_ROW_ORDER = [
  "1",
  "1a",
  "2",
  "3",
  "4",
  "5",
  "6",
  "7",
  "8",
  "9",
  "10",
] as const;

/* ---- Map HUD rows + constraints (GET /ledger) ---- */

export type LedgerRowStatus =
  | "counted"
  | "partial"
  | "not_yet"
  | "excluded";

export type LedgerTag =
  | "market"
  | "proxy"
  | "shadow"
  | "market_or_proxy"
  | "reported"
  | "already_included"
  | "nested";

export type LedgerRow = {
  id: string;
  label: string;
  /** Nested under parent (e.g. 1a under 1); never added as a sibling total. */
  parent_id: string | null;
  nested: boolean;
  tag: LedgerTag;
  status: LedgerRowStatus;
  /** Honest status copy; "not yet" must never appear as £0. */
  status_note: string;
  /** Public amount placeholder — never a modelled AGR £ figure. */
  amount_placeholder: string;
  /** Outside Scottish headline + shadow totals (row 9). */
  outside_scottish_total?: boolean;
};

export type LedgerConstraint = {
  id: string;
  label: string;
  /** Constraint rule — never a rent figure. */
  rule: string;
};

export type LedgerPayload = {
  version: number;
  brief: string;
  publication_note: string;
  rows: LedgerRow[];
  constraints: LedgerConstraint[];
  source: "api" | "fixture";
};

export type LedgerToggleState = Record<string, boolean>;

/** Spec rows 1–10 + nested 1a (order preserved for the HUD). */
export const LEDGER_FIXTURE_ROWS: LedgerRow[] = [
  {
    id: "1",
    label: "Surface site rent",
    parent_id: null,
    nested: false,
    tag: "market_or_proxy",
    status: "not_yet",
    status_note:
      "Best permitted use. Figures are being checked and aren't published yet.",
    amount_placeholder: "—",
  },
  {
    id: "1a",
    label: "Planning uplift",
    parent_id: "1",
    nested: true,
    tag: "already_included",
    status: "not_yet",
    status_note:
      "Already included in Surface site rent — never added as a sibling total.",
    amount_placeholder: "—",
  },
  {
    id: "2",
    label: "Mineral rent",
    parent_id: null,
    nested: false,
    tag: "proxy",
    status: "not_yet",
    status_note: "Royalty/tonne, below ground. Not yet on the public ledger.",
    amount_placeholder: "—",
  },
  {
    id: "3",
    label: "Onshore wind + hydro resource rent",
    parent_id: null,
    nested: false,
    tag: "proxy",
    status: "partial",
    status_note:
      "Site rent minus footprint surface rent. Inventory layers may paint.",
    amount_placeholder: "—",
  },
  {
    id: "4",
    label: "Seabed & foreshore",
    parent_id: null,
    nested: false,
    tag: "market",
    status: "not_yet",
    status_note: "CES offshore wind, cables, moorings, foreshore.",
    amount_placeholder: "—",
  },
  {
    id: "5",
    label: "Aquaculture licence rent",
    parent_id: null,
    nested: false,
    tag: "shadow",
    status: "not_yet",
    status_note: "Value with no market price — total minus CES seabed paid.",
    amount_placeholder: "—",
  },
  {
    id: "6",
    label: "Fisheries quota",
    parent_id: null,
    nested: false,
    tag: "market_or_proxy",
    status: "not_yet",
    status_note: "Market if lease prices, else shadow.",
    amount_placeholder: "—",
  },
  {
    id: "7",
    label: "Water scarcity",
    parent_id: null,
    nested: false,
    tag: "shadow",
    status: "not_yet",
    status_note: "Value with no market price — not yet published.",
    amount_placeholder: "—",
  },
  {
    id: "8",
    label: "Unpriced peat/soil carbon",
    parent_id: null,
    nested: false,
    tag: "shadow",
    status: "not_yet",
    status_note: "Only unpriced carbon; timber/credits stay in row 1.",
    amount_placeholder: "—",
  },
  {
    id: "9",
    label: "Oil & gas",
    parent_id: null,
    nested: false,
    tag: "reported",
    status: "excluded",
    status_note: "Offshore, outside the Scottish land total.",
    amount_placeholder: "—",
    outside_scottish_total: true,
  },
  {
    id: "10",
    label: "Ecosystem services",
    parent_id: null,
    nested: false,
    tag: "shadow",
    status: "not_yet",
    status_note: "Value with no market price — later.",
    amount_placeholder: "—",
  },
];

export const LEDGER_FIXTURE_CONSTRAINTS: LedgerConstraint[] = [
  {
    id: "designations",
    label: "Designations",
    rule: "Constraint: changes best use, adds no value",
  },
  {
    id: "flood",
    label: "Flood",
    rule: "Constraint: changes best use, adds no value",
  },
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
];

export const LEDGER_FIXTURE: LedgerPayload = {
  version: 1,
  brief: "Annual Ground Rent breakdown: where the value comes from",
  publication_note:
    "Figures are being checked and aren't published yet.",
  rows: LEDGER_FIXTURE_ROWS,
  constraints: LEDGER_FIXTURE_CONSTRAINTS,
  source: "fixture",
};

function normalizePayload(raw: unknown, source: "api" | "fixture"): LedgerPayload {
  if (!raw || typeof raw !== "object") {
    throw new Error("Ledger response missing body");
  }
  const body = raw as Partial<LedgerPayload>;
  if (!Array.isArray(body.rows) || !Array.isArray(body.constraints)) {
    throw new Error("Ledger response missing rows or constraints");
  }
  return {
    version: typeof body.version === "number" ? body.version : 1,
    brief: body.brief || LEDGER_FIXTURE.brief,
    publication_note: body.publication_note || LEDGER_FIXTURE.publication_note,
    rows: body.rows as LedgerRow[],
    constraints: body.constraints as LedgerConstraint[],
    source,
  };
}

/**
 * Fetch GET /ledger. On 404 / offline API, return the local fixture so the HUD
 * stays aligned with the accounting rules while the API is unavailable.
 */
export async function fetchLedger(): Promise<LedgerPayload> {
  try {
    const payload = await apiJson<LedgerPayload>("/ledger");
    return normalizePayload(payload, "api");
  } catch (err: unknown) {
    if (err instanceof ApiError && (err.status === 404 || err.status === 503)) {
      return { ...LEDGER_FIXTURE, source: "fixture" };
    }
    // Network / offline: still show the ledger skeleton rather than a blank tools panel.
    if (err instanceof ApiError && (err.status == null || err.status >= 500)) {
      return { ...LEDGER_FIXTURE, source: "fixture" };
    }
    throw new Error(visitorFacingError(err));
  }
}

export function tagLabel(tag: LedgerTag): string {
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
      return "outside";
    case "already_included":
      return "already included";
    case "nested":
      return "already included";
    default: {
      const _exhaustive: never = tag;
      return _exhaustive;
    }
  }
}

export function statusLabel(status: LedgerRowStatus): string {
  switch (status) {
    case "counted":
      return "counted";
    case "partial":
      return "partial";
    case "not_yet":
      return "not yet";
    case "excluded":
      return "excluded";
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

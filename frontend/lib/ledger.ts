/** Natural capital ledger catalog from GET /api/ledger.json */

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

export type LedgerCatalog = {
  version: number;
  kind: string;
  brief?: string;
  spec?: string;
  grain?: string;
  checks: LedgerCheck[];
  excluded: LedgerExcluded[];
  benchmarks: LedgerBenchmark[];
  benchmark_label: string;
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

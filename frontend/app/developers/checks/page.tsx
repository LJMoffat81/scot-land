"use client";

import { useEffect, useState } from "react";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { apiJson } from "@/lib/api";
import {
  CHECK_MEANINGS,
  type CheckMeaningId,
} from "@/lib/checkMeanings";
import {
  LEDGER_CHECK_ORDER,
  type LedgerCatalog,
  type LedgerCheck,
  type LedgerTestLogEntry,
} from "@/lib/ledger";

/** Known calibration / class failures — shown as "Known issue", not hidden. */
const KNOWN_ISSUE_IDS = new Set([
  "ur6_class_2_job_access_gradient",
  "yield_at_cap",
  "yield_class_capped",
]);

function shortenRunId(runHash: string): string {
  if (!runHash) return "—";
  return runHash.length <= 12 ? runHash : `${runHash.slice(0, 12)}…`;
}

function entryLabel(entry: LedgerTestLogEntry): string {
  if (
    entry.status === "fail" &&
    (KNOWN_ISSUE_IDS.has(entry.id) ||
      /yield.*cap|ur6|class.?2/i.test(entry.id) ||
      /yield.*cap|ur6|class.?2/i.test(entry.detail))
  ) {
    return "Known issue";
  }
  return entry.status;
}

function hasKnownIssue(check: LedgerCheck): boolean {
  return check.test_log.some((entry) => entryLabel(entry) === "Known issue");
}

export default function DevelopersChecksPage() {
  const [data, setData] = useState<LedgerCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    void apiJson<LedgerCatalog>("/api/ledger.json")
      .then((body) => {
        setData(body);
        setError(null);
      })
      .catch(() => {
        setData(null);
        setError("Breakdown catalog unavailable.");
      });
  }, []);

  const checks = data?.checks ?? [];
  const ordered = LEDGER_CHECK_ORDER.map((id) =>
    checks.find((c) => c.id === id),
  ).filter((c): c is NonNullable<typeof c> => Boolean(c));

  async function copyRunId(check: LedgerCheck) {
    try {
      await navigator.clipboard.writeText(check.run_hash);
      setCopiedId(check.id);
      window.setTimeout(() => setCopiedId(null), 1500);
    } catch {
      setCopiedId(null);
    }
  }

  return (
    <main
      className="downloads-page data-ledger-page"
      data-testid="developers-checks-page"
    >
      <SiteNav current="developers" />
      <h1>Technical checks</h1>
      <ResearchBanner />
      <p>
        Automatic tests that check our sums follow the rules. They are for
        developers and reviewers. Source catalogue and excluded list:{" "}
        <a href="/data">Data &amp; sources</a>.
      </p>
      <p className="downloads-note" data-testid="developers-checks-yield-note">
        Signed-off land yield v3 (central 4.499%, band 3.98–4.50%, hash{" "}
        <code>4654e513</code>) comes from shared surface config. Public money
        figures stay blocked; visitors do not see these amounts on How it works.
      </p>
      {error && <p className="downloads-note">{error}</p>}

      <div className="checks-table-wrap">
        <table className="checks-table" data-testid="developers-checks-table">
          <thead>
            <tr>
              <th scope="col">Check</th>
              <th scope="col">What it makes sure of</th>
              <th scope="col">Result</th>
              <th scope="col">Run ID</th>
              <th scope="col">Test log</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((check) => (
              <tr key={check.id} data-check-id={check.id}>
                <td>
                  <code className="check-id">{check.id}</code>{" "}
                  <span className="check-meaning">
                    {CHECK_MEANINGS[check.id as CheckMeaningId]}
                  </span>
                </td>
                <td>{check.meaning}</td>
                <td>
                  <span
                    className={`ledger-result ledger-result-${check.result}`}
                    data-result={check.result}
                  >
                    {hasKnownIssue(check) && check.result === "pass"
                      ? "pass (known issues in log)"
                      : check.result}
                  </span>
                </td>
                <td>
                  <button
                    type="button"
                    className="run-id-copy"
                    title={check.run_hash}
                    onClick={() => void copyRunId(check)}
                    data-testid={`run-id-${check.id}`}
                  >
                    <code>{shortenRunId(check.run_hash)}</code>
                    <span className="download-path">
                      {copiedId === check.id ? "Copied full ID" : "Copy full ID"}
                    </span>
                  </button>
                </td>
                <td>
                  {/* Item 3: real log entries as plain text — never a fake link. */}
                  <ul className="check-test-log" data-testid={`test-log-${check.id}`}>
                    {check.test_log.map((entry) => (
                      <li key={entry.id}>
                        <span
                          className={`ledger-result ledger-result-${entry.status}`}
                          data-log-status={entryLabel(entry)}
                        >
                          {entryLabel(entry)}
                        </span>{" "}
                        <code>{entry.id}</code> — {entry.detail}
                      </li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!error && ordered.length === 0 && (
        <p className="downloads-note">Loading checks…</p>
      )}
    </main>
  );
}

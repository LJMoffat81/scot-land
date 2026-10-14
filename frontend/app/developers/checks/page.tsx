"use client";

import { useEffect, useState } from "react";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { apiJson } from "@/lib/api";
import {
  LEDGER_CHECK_ORDER,
  type LedgerCatalog,
} from "@/lib/ledger";

export default function DevelopersChecksPage() {
  const [data, setData] = useState<LedgerCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void apiJson<LedgerCatalog>("/api/ledger.json")
      .then((body) => {
        setData(body);
        setError(null);
      })
      .catch(() => {
        setData(null);
        setError("Ledger catalog unavailable.");
      });
  }, []);

  const checks = data?.checks ?? [];
  const ordered = LEDGER_CHECK_ORDER.map((id) =>
    checks.find((c) => c.id === id),
  ).filter((c): c is NonNullable<typeof c> => Boolean(c));

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
      {error && <p className="downloads-note">{error}</p>}

      <ul className="ledger-check-list">
        {ordered.map((check) => (
          <li key={check.id} className="ledger-check">
            <div className="ledger-check-head">
              <strong>{check.id}</strong>
              <span
                className={`ledger-result ledger-result-${check.result}`}
                data-result={check.result}
              >
                {check.result}
              </span>
            </div>
            <p className="ledger-check-meaning">{check.meaning}</p>
            <p className="download-path">
              run hash <code>{check.run_hash}</code>
            </p>
            <details className="ledger-test-log">
              <summary>Pre-registered test log</summary>
              <ul>
                {check.test_log.map((entry) => (
                  <li key={entry.id}>
                    <span
                      className={`ledger-result ledger-result-${entry.status}`}
                    >
                      {entry.status}
                    </span>{" "}
                    <code>{entry.id}</code> — {entry.detail}
                  </li>
                ))}
              </ul>
            </details>
          </li>
        ))}
      </ul>
      {!error && ordered.length === 0 && (
        <p className="downloads-note">Loading checks…</p>
      )}
    </main>
  );
}

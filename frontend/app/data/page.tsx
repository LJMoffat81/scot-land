"use client";

import { useEffect, useState } from "react";
import { apiJson } from "../../lib/api";
import {
  LEDGER_CHECK_ORDER,
  type LedgerCatalog,
} from "../../lib/ledger";

function DataNav() {
  return (
    <p className="downloads-nav">
      <a href="/">Map</a>
      {" · "}
      <a href="/data" aria-current="page">
        Data
      </a>
      {" · "}
      <a href="/downloads">Downloads</a>
      {" · "}
      <a href="/open-api">Public API</a>
      {" · "}
      <a href="/mission">Mission</a>
      {" · "}
      <a href="/methodology">Methodology</a>
    </p>
  );
}

export default function DataChecksPage() {
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
    <main className="downloads-page data-ledger-page">
      <DataNav />
      <h1>Data — licences, checks &amp; excluded</h1>
      <p>
        Natural capital ledger accounting checks, the excluded list, and links
        to layer licences. Driven by the catalog API (
        <code>/api/ledger.json</code>), not a map-panel layer dump. Research
        estimate, not an official valuation or bill. Figures pending sign-off.
        Full sources table: <a href="/methodology#sources">Methodology</a>.
      </p>
      {data?.grain && <p className="downloads-note">{data.grain}</p>}
      {error && <p className="downloads-note">{error}</p>}

      <h2>Checks</h2>
      <p className="downloads-note">
        Every check shows pass/fail, a run hash, and its pre-registered test
        log (including known failures such as UR6 class 2 and yield at cap).
      </p>
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

      <h2>Excluded</h2>
      <p className="downloads-note">
        Always listed with reasons. Oil &amp; gas is reported outside the
        Scottish total, not silently dropped.
      </p>
      <ul>
        {(data?.excluded ?? []).map((item) => (
          <li key={item.id}>
            <strong>{item.label}</strong>
            <span className="download-path">{item.reason}</span>
          </li>
        ))}
      </ul>

      <h2>Benchmarks</h2>
      <p className="downloads-note">
        Shown beside the ledger and labelled{" "}
        <strong>{data?.benchmark_label ?? "benchmark only, not inputs"}</strong>
        . Never fed into headline or shadow totals.
      </p>
      <ul className="ledger-benchmarks">
        {(data?.benchmarks ?? []).map((b) => (
          <li key={b.id}>
            <strong>{b.label}</strong>
            <span className="download-path ledger-not-input">{b.note}</span>
          </li>
        ))}
      </ul>
    </main>
  );
}

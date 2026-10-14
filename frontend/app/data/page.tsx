"use client";

import { useEffect, useState } from "react";
import HashRedirect from "@/components/HashRedirect";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { apiJson } from "../../lib/api";
import { type LedgerCatalog } from "../../lib/ledger";

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

  return (
    <main className="downloads-page data-ledger-page">
      <HashRedirect fromHash="checks" to="/developers/checks" />
      <SiteNav current="data" />
      <h1>Data &amp; sources</h1>
      <ResearchBanner />
      <p>
        Scot-LAND uses open, public data only. Every layer shows its licence.
        Full sources table:{" "}
        <a href="/methodology#sources">How it works</a>. Technical checks for
        developers: <a href="/developers/checks">Technical checks</a>.
      </p>
      {data?.grain && <p className="downloads-note">{data.grain}</p>}
      {error && <p className="downloads-note">{error}</p>}

      <h2 id="gaps">Gaps we know about</h2>
      <p className="downloads-note">
        Missing map cells use grey hatch and <strong>No data</strong>. Roll-up
        and surface rent crosswalk work continues; private owners stay hidden.
      </p>

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

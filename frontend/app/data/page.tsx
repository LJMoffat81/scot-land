"use client";

import { useEffect, useState } from "react";
import GlossaryBox from "@/components/GlossaryBox";
import HashRedirect from "@/components/HashRedirect";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { apiJson } from "../../lib/api";

type CatalogLayer = {
  id: string;
  label: string;
  description?: string;
  licence?: string;
  licence_url?: string;
  source_url?: string;
  status?: string;
};

type CatalogPayload = {
  layers?: CatalogLayer[];
};

/**
 * Data & sources — site rewrite section B (wording pending Laurie approval).
 * Sources table reads /api/catalog.json; rows need a licence_url.
 */
export default function DataChecksPage() {
  const [layers, setLayers] = useState<CatalogLayer[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void apiJson<CatalogPayload>("/api/catalog.json")
      .then((body) => {
        const withLicence = (body.layers ?? []).filter(
          (layer) => Boolean(layer.licence_url?.trim()),
        );
        setLayers(withLicence);
        setError(null);
      })
      .catch(() => {
        setLayers([]);
        setError("Source catalogue unavailable.");
      });
  }, []);

  return (
    <main className="downloads-page data-ledger-page methodology-page">
      <HashRedirect fromHash="checks" to="/developers/checks" />
      <SiteNav current="data" />
      <h1>Data &amp; sources</h1>
      <ResearchBanner />
      <p>
        Scot-LAND uses open, public data only. Every layer shows its licence.
        Here is what we use, what we only link to, and what we leave out.
      </p>

      <h2 id="sources">Sources on the map</h2>
      <p className="downloads-note">
        Built from the open source catalogue. A source appears only when its
        licence link is set.
      </p>
      {error ? <p className="downloads-note">{error}</p> : null}
      <div className="sources-table-wrap">
        <table className="sources-table" data-testid="data-sources-table">
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">What it shows</th>
              <th scope="col">Licence</th>
              <th scope="col">Link</th>
            </tr>
          </thead>
          <tbody>
            {layers.map((layer) => (
              <tr key={layer.id} data-source-id={layer.id}>
                <td>{layer.label}</td>
                <td>{layer.description || "—"}</td>
                <td>
                  {layer.licence_url ? (
                    <a
                      href={layer.licence_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {layer.licence || "Licence"}
                    </a>
                  ) : (
                    layer.licence || "—"
                  )}
                </td>
                <td>
                  {layer.source_url ? (
                    <a
                      href={layer.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Source
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Linked, not copied</h2>
      <p>
        ScotLIS (the official title record), Common Good registers, Crofting
        Register maps on RoS, Spatial Hub layers that need a login.
      </p>

      <h2>Left out, and why</h2>
      <ul>
        <li>
          Who Owns Scotland and other paid ownership data: paid.
        </li>
        <li>Full British Geological Survey minerals data: paid.</li>
        <li>
          Property website listings (Zoopla, Rightmove and others): not allowed.
        </li>
        <li>Names of individual crofters: personal data.</li>
        <li>
          Layers without a clear open licence: kept off until the licence is
          confirmed.
        </li>
        <li>
          Oil and gas: shown separately, outside Scotland&apos;s totals, because
          it is managed by the UK.
        </li>
      </ul>

      <h2 id="gaps">Gaps we know about</h2>
      <ul>
        <li>Old land records not yet digital.</li>
        <li>Private owners (we never show them).</li>
        <li>Natural-resource figures not yet split by Data Zone.</li>
        <li>Edinburgh&apos;s planning allocations.</li>
        <li>National common grazings boundaries.</li>
        <li>
          Land figures still on the 2011 Data Zones while we move to the 2022
          set.
        </li>
      </ul>

      <h2>Comparisons</h2>
      <p>
        Some outside estimates are shown for comparison only. They never feed
        into our figures.
      </p>

      <GlossaryBox />

      <p className="meta">
        <a href="/developers/checks">Technical checks for developers</a>
        {" · "}
        <a href="/methodology">How it works</a>
        {" · "}
        <a href="/">Back to map</a>
      </p>
    </main>
  );
}

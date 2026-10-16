"use client";

import { useEffect, useMemo, useState } from "react";
import GlossaryBox from "@/components/GlossaryBox";
import HashRedirect from "@/components/HashRedirect";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { groupCatalogSources } from "@/lib/dataSourceGroups";
import { apiJson } from "../../lib/api";

type CatalogLayer = {
  id: string;
  label: string;
  description?: string;
  licence?: string;
  licence_url?: string;
  source_url?: string;
  status?: string;
  group?: string;
  ledger_role?: string | null;
  ledger_row?: string | null;
};

type CatalogPayload = {
  layers?: CatalogLayer[];
};

function asText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  return String(value);
}

/**
 * Data & sources — grouped Land / Resources / Nature / Limits.
 * Sources table reads /api/catalog.json; rows need a licence_url.
 * Hardened against catalogue shape surprises (site-watch PR B item 7).
 */
export default function DataChecksPage() {
  const [layers, setLayers] = useState<CatalogLayer[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void apiJson<CatalogPayload>("/api/catalog.json")
      .then((body) => {
        const raw = Array.isArray(body?.layers) ? body.layers : [];
        const withLicence = raw.filter((layer) => {
          if (!layer || typeof layer !== "object") return false;
          const id = asText((layer as CatalogLayer).id).trim();
          const licenceUrl = asText((layer as CatalogLayer).licence_url).trim();
          return Boolean(id && licenceUrl);
        }) as CatalogLayer[];
        setLayers(withLicence);
        setError(null);
      })
      .catch(() => {
        setLayers([]);
        setError("Source catalogue unavailable.");
      });
  }, []);

  const groups = useMemo(() => {
    try {
      return groupCatalogSources(layers);
    } catch (err) {
      console.error("data sources grouping failed", err);
      return [];
    }
  }, [layers]);

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
      <p className="downloads-note" data-testid="data-sources-summary">
        Built from the open source catalogue. A source appears only when its
        licence link is set. Sources are grouped as Land, Natural resource rents,
        Services of nature and Limits — open a group to see the rows.
      </p>
      {error ? <p className="downloads-note">{error}</p> : null}
      <div className="sources-groups" data-testid="data-sources-groups">
        {groups.map((bucket) => (
          <details
            key={bucket.key}
            className="sources-group"
            data-testid={`data-sources-group-${bucket.key}`}
            open={bucket.key === "land"}
          >
            <summary className="sources-group-summary">
              <span className="sources-group-title">{bucket.label}</span>
              <span className="sources-group-count">
                {bucket.layers.length}
              </span>
            </summary>
            <p className="downloads-note sources-group-blurb">{bucket.summary}</p>
            {/* Desktop: wide table. Mobile (below 640px): stacked cards — SW-034. */}
            <div className="sources-table-wrap">
              <table
                className="sources-table"
                data-testid={`data-sources-table-${bucket.key}`}
              >
                <thead>
                  <tr>
                    <th scope="col">Source</th>
                    <th scope="col">What it shows</th>
                    <th scope="col">Licence</th>
                    <th scope="col">Link</th>
                  </tr>
                </thead>
                <tbody>
                  {bucket.layers.map((layer) => (
                    <tr key={asText(layer.id)} data-source-id={asText(layer.id)}>
                      <td>{asText(layer.label) || asText(layer.id)}</td>
                      <td>{asText(layer.description) || "—"}</td>
                      <td>
                        {asText(layer.licence_url) ? (
                          <a
                            href={asText(layer.licence_url)}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {asText(layer.licence) || "Licence"}
                          </a>
                        ) : (
                          asText(layer.licence) || "—"
                        )}
                      </td>
                      <td>
                        {asText(layer.source_url) ? (
                          <a
                            href={asText(layer.source_url)}
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
            <ul
              className="sources-card-list"
              data-testid={`data-sources-cards-${bucket.key}`}
            >
              {bucket.layers.map((layer) => {
                const id = asText(layer.id);
                const name = asText(layer.label) || id;
                const licenceUrl = asText(layer.licence_url);
                const sourceUrl = asText(layer.source_url);
                return (
                  <li
                    key={id}
                    className="sources-card"
                    data-testid={`data-source-card-${id}`}
                    data-source-id={id}
                  >
                    <p className="sources-card-name">{name}</p>
                    <p className="sources-card-group">{bucket.label}</p>
                    <p className="sources-card-licence">
                      {licenceUrl ? (
                        <a
                          href={licenceUrl}
                          target="_blank"
                          rel="noreferrer"
                          data-testid={`data-source-licence-${id}`}
                        >
                          {asText(layer.licence) || "Licence"}
                        </a>
                      ) : (
                        asText(layer.licence) || "—"
                      )}
                    </p>
                    <p className="sources-card-link">
                      {sourceUrl ? (
                        <a
                          href={sourceUrl}
                          target="_blank"
                          rel="noreferrer"
                          data-testid={`data-source-link-${id}`}
                        >
                          Source
                        </a>
                      ) : (
                        "—"
                      )}
                    </p>
                  </li>
                );
              })}
            </ul>
          </details>
        ))}
      </div>

      <h2>Linked, not copied</h2>
      <p>
        ScotLIS (the official title record), Common Good registers, Crofting
        Register maps on RoS, Spatial Hub layers that need a login.
      </p>

      <h2>Left out, and why</h2>
      <ul>
        <li>Who Owns Scotland and other paid ownership data: paid.</li>
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
          Oil and gas: kept separate from Scotland&apos;s land figures, because
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

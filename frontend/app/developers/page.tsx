"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import CopyCodeButton from "@/components/CopyCodeButton";
import QualityTag from "@/components/QualityTag";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import {
  formatDownloadBytes,
  type DownloadManifest,
} from "@/lib/downloadManifest";
import { QUALITY_TAGS } from "@/lib/qualityTag";

const GITHUB_REPO = "https://github.com/LJMoffat81/scot-land";

/** API addresses — each appears once on this page, in #api only (item 4). */
const API_ROWS = [
  {
    id: "api-place",
    what: "One place",
    path: "/api/place.json?pc=EH1+1YZ",
    tryIt: true,
  },
  {
    id: "api-catalog",
    what: "Source catalogue",
    path: "/api/catalog.json",
    tryIt: false,
  },
  {
    id: "api-ledger",
    what: "Land rent ledger (structure and rules; no £ yet)",
    path: "/api/ledger.json",
    tryIt: false,
  },
  {
    id: "api-vdl",
    what: "Vacant and derelict land",
    path: "/api/vdl.json",
    tryIt: false,
  },
  {
    id: "api-ldp",
    what: "Planned land use",
    path: "/api/ldp.json",
    tryIt: false,
  },
  {
    id: "api-registers",
    what: "Official registers",
    path: "/api/registers.json",
    tryIt: false,
  },
  {
    id: "api-common-good",
    what: "Common Good registers",
    path: "/api/common-good.json",
    tryIt: false,
  },
  {
    id: "api-crofting",
    what: "Crofting",
    path: "/api/crofting.json",
    tryIt: false,
  },
] as const;

const LAYERS_BBOX =
  "/layers/…?south=&west=&north=&east=";

function DevelopersPageInner() {
  const searchParams = useSearchParams();
  const showMovedNote = searchParams.get("moved") === "1";
  const [manifest, setManifest] = useState<DownloadManifest | null>(null);
  const [manifestError, setManifestError] = useState<string | null>(null);

  useEffect(() => {
    void fetch("/downloads/manifest.json", { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) throw new Error(`manifest ${res.status}`);
        return (await res.json()) as DownloadManifest;
      })
      .then((body) => {
        setManifest(body);
        setManifestError(null);
      })
      .catch(() => {
        setManifest(null);
        setManifestError("Download list unavailable.");
      });
  }, []);

  return (
    <main className="downloads-page developers-page" data-testid="developers-page">
      <SiteNav current="developers" />
      <h1>Downloads &amp; API</h1>
      <ResearchBanner />
      {showMovedNote ? (
        <p className="downloads-note" data-testid="developers-moved-note">
          This page has moved to Downloads &amp; API.
        </p>
      ) : null}
      <p>
        Use Scot-LAND&apos;s open data in your own work. Everything here is free
        under the licence shown. Please say where it came from.
      </p>
      <p className="downloads-note" data-testid="quality-tag-inline">
        Input quality tags:{" "}
        <span className="quality-tag-inline">
          {QUALITY_TAGS.map((tag, i) => (
            <span key={tag}>
              <QualityTag quality={tag} />
              {i < QUALITY_TAGS.length - 2 ? ", " : null}
              {i === QUALITY_TAGS.length - 2 ? " and " : null}
            </span>
          ))}
        </span>
        . Annual Ground Rent amounts are not a public download.
      </p>

      <section id="downloads" data-testid="developers-downloads">
        <h2>Download files</h2>
        <p className="downloads-note">
          One card per bundle. Until a packaged file exists, use{" "}
          <strong>JSON (for developers)</strong> to jump to the API section.
        </p>
        {manifestError ? (
          <p className="downloads-note">{manifestError}</p>
        ) : null}
        <ul className="download-card-list">
          {(manifest?.bundles ?? []).map((bundle) => {
            const hasFile = Boolean(bundle.href && bundle.file);
            return (
              <li
                key={bundle.id}
                className="download-card"
                data-testid={`download-card-${bundle.id}`}
                data-has-file={hasFile ? "true" : "false"}
              >
                <h3 className="download-card-name">{bundle.name}</h3>
                <p className="download-card-desc">{bundle.whats_in_it}</p>
                <dl className="download-card-meta">
                  <div>
                    <dt>Format</dt>
                    <dd>{bundle.format}</dd>
                  </div>
                  <div>
                    <dt>Size</dt>
                    <dd>{formatDownloadBytes(bundle.bytes)}</dd>
                  </div>
                  <div>
                    <dt>Licence</dt>
                    <dd>{bundle.licence}</dd>
                  </div>
                  <div>
                    <dt>Updated</dt>
                    <dd>{bundle.updated}</dd>
                  </div>
                  {bundle.zone_set ? (
                    <div data-testid={`download-zone-set-${bundle.id}`}>
                      <dt title="Which Data Zone map these figures use">
                        Zone set
                      </dt>
                      <dd>
                        <span>{bundle.zone_set}</span>
                        <span className="download-path">
                          {" "}
                          — Which Data Zone map these figures use
                        </span>
                      </dd>
                    </div>
                  ) : null}
                </dl>
                {hasFile && bundle.href ? (
                  <a
                    className="download-card-action"
                    href={bundle.href}
                    download={bundle.file ?? undefined}
                    data-testid={`download-file-${bundle.id}`}
                  >
                    Download
                  </a>
                ) : (
                  <a
                    className="download-card-action download-card-action-json"
                    href={`#${bundle.api_anchor}`}
                    data-testid={`download-json-${bundle.id}`}
                  >
                    JSON (for developers)
                  </a>
                )}
              </li>
            );
          })}
        </ul>
        {!manifestError && !manifest ? (
          <p className="downloads-note">Loading downloads…</p>
        ) : null}
      </section>

      <section id="api" data-testid="developers-api">
        <h2>API (for developers)</h2>
        <p>
          Ask for data about one place, or the area on screen. Answers come back
          as JSON. If a layer is not loaded, the API answers &lsquo;temporarily
          unavailable&rsquo;.
        </p>
        <div className="api-table-wrap">
          <table className="api-table" data-testid="developers-api-table">
            <thead>
              <tr>
                <th scope="col">What you get</th>
                <th scope="col">Address</th>
                <th scope="col">Try it</th>
              </tr>
            </thead>
            <tbody>
              {API_ROWS.map((row) => (
                <tr key={row.id} id={row.id}>
                  <td>{row.what}</td>
                  <td>
                    <div className="api-address">
                      <code className="api-path-code">{row.path}</code>
                      <CopyCodeButton value={row.path} />
                    </div>
                  </td>
                  <td>
                    {row.tryIt ? (
                      <a href={row.path} data-testid={`try-it-${row.id}`}>
                        Try it
                      </a>
                    ) : (
                      <span className="downloads-note">—</span>
                    )}
                  </td>
                </tr>
              ))}
              <tr id="api-layers">
                <td>Map layers for the area on screen</td>
                <td>
                  <div className="api-address">
                    {/* Item 3: bbox pattern is plain code, never a link. */}
                    <code className="api-path-code">{LAYERS_BBOX}</code>
                    <CopyCodeButton value={LAYERS_BBOX} />
                  </div>
                  <p className="download-path">
                    Listed in the{" "}
                    <a href="/developers/api">API reference</a>, in a code box,
                    not shown as links.
                  </p>
                </td>
                <td>
                  <span className="downloads-note">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p>
          <a href="/developers/api">Full API reference</a>
          {" · "}
          <a href="/developers/checks">Technical checks</a>
          {" · "}
          <a href={GITHUB_REPO} target="_blank" rel="noreferrer">
            Source code
          </a>
        </p>
      </section>
    </main>
  );
}

export default function DevelopersPage() {
  return (
    <Suspense
      fallback={
        <main className="downloads-page developers-page">
          <SiteNav current="developers" />
          <ResearchBanner />
          Loading…
        </main>
      }
    >
      <DevelopersPageInner />
    </Suspense>
  );
}

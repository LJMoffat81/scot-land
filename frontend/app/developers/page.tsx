"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import QualityTag from "@/components/QualityTag";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import {
  formatDownloadBytes,
  type DownloadManifest,
} from "@/lib/downloadManifest";
import { QUALITY_TAGS } from "@/lib/qualityTag";

function DevelopersPageInner() {
  const searchParams = useSearchParams();
  // Keep the hook check (tests + soft nav). Also read window.location because the
  // Full Route Cache serves this page with empty server searchParams ("q":""), so
  // useSearchParams alone misses ?moved=1 on hard loads after deploy.
  const movedFromHook = searchParams.get("moved") === "1";
  const [movedFromUrl, setMovedFromUrl] = useState(false);
  const [hashTarget, setHashTarget] = useState("");
  const showMovedNote = movedFromHook || movedFromUrl;
  const showDownloadsMovedNote = showMovedNote && hashTarget === "downloads";
  const showApiMovedNote = showMovedNote && hashTarget === "api";
  const [manifest, setManifest] = useState<DownloadManifest | null>(null);
  const [manifestError, setManifestError] = useState<string | null>(null);

  useEffect(() => {
    setMovedFromUrl(
      new URLSearchParams(window.location.search).get("moved") === "1",
    );
    setHashTarget(window.location.hash.replace(/^#/, ""));
  }, []);

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
      <h1>Get the data</h1>
      <ResearchBanner />
      <p>
        Use Scot-LAND&apos;s open data in your own work. The map and the files
        on this page are free to use under the licence shown. Please say where
        they came from. Larger data packs and a full API may be paid services
        later.
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
        . These describe where the input data comes from. On the map, figures
        are labelled Market, Modelled or Estimate. Annual Ground Rent amounts
        are not a public download.
      </p>

      <section id="downloads" data-testid="developers-downloads">
        {/* Inside #downloads so ?moved=1#downloads keeps the note in view after hash scroll. */}
        {showDownloadsMovedNote ? (
          <p className="downloads-note" data-testid="developers-moved-note">
            Downloads has moved here.
          </p>
        ) : null}
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
                <p
                  className="download-card-summary"
                  data-testid={`download-summary-${bundle.id}`}
                >
                  <span
                    className="download-card-size"
                    data-testid={`download-size-${bundle.id}`}
                  >
                    {hasFile
                      ? formatDownloadBytes(bundle.bytes)
                      : "Not packaged yet"}
                  </span>
                  <span className="download-card-summary-sep" aria-hidden="true">
                    ·
                  </span>
                  <span className="download-card-desc">{bundle.whats_in_it}</span>
                </p>
                <dl className="download-card-meta">
                  <div>
                    <dt>Format</dt>
                    <dd>{bundle.format}</dd>
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
                    href="/developers/api"
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
        {/* Inside #api so ?moved=1#api keeps the note in view after hash scroll. */}
        {showApiMovedNote ? (
          <p className="downloads-note" data-testid="developers-api-moved-note">
            The API page has moved here.
          </p>
        ) : null}
        <h2>API (for developers)</h2>
        <p>
          <a href="/developers/api">Developer API and bulk data</a>
          {" · "}
          <a href="/developers/checks">Technical checks</a>
          {" · "}
          <a href="/developers/glossary">Glossary</a>
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

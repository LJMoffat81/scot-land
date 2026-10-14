"use client";

import { useEffect, useState } from "react";
import QualityTag from "@/components/QualityTag";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { apiJson } from "@/lib/api";
import { withExportVersion } from "@/lib/exportUrl";
import { QUALITY_TAGS } from "@/lib/qualityTag";

type DownloadItem = {
  id: string;
  label: string;
  licence?: string;
  url?: string;
  endpoint?: string;
  note?: string;
};

type Downloads = { note?: string; items?: DownloadItem[] };

const OPEN_JSON = [
  {
    href: "/api/vdl.json",
    name: "Vacant and derelict land, from the Scottish Vacant and Derelict Land Survey",
  },
  {
    href: "/api/ldp.json",
    name: "LDP allocations — PostGIS coverage and honest national gaps",
  },
  {
    href: "/api/place.json?pc=EH1+1YZ",
    name: "One place, as an example (Edinburgh EH1 1YZ)",
  },
  {
    href: "/api/catalog.json",
    name: "What is on the map, what is only linked, and what is missing",
  },
  {
    href: "/api/ledger.json",
    name: "Natural capital ledger — rows 1–10 (+1a), checks, excluded, benchmarks (not inputs)",
  },
  {
    href: "/api/registers.json",
    name: "Official register pages",
  },
  {
    href: "/api/common-good.json",
    name: "Common Good registers — verified links and gaps",
  },
  {
    href: "/api/crofting.json",
    name: "Crofting Register + common grazings — OGL tables and spatial gaps",
  },
];

const SOURCE_NAME: Record<string, string> = {
  vdl_register: "Scottish Vacant and Derelict Land Survey",
  ldp_allocations: "Local Development Plan allocations (Spatial Hub / OGL)",
  inspire_parcels: "Registers of Scotland open land map",
  nfi_overlay: "National Forest Inventory woodland (PostGIS)",
  native_woodland_overlay: "Native Woodland Survey of Scotland (PostGIS)",
  scotwind_intog: "ScotWind / INTOG seabed option polygons (CES)",
  common_good: "Common Good registers (linked; Highland licence unconfirmed)",
  crofting_register: "Crofting Register of Crofts (OGL; map extents on RoS)",
  common_grazings: "Common grazings (OGL list; no national open polygon)",
  scotlis: "ScotLIS, the official title record",
};

const MINTLIFY_INTRO =
  "https://github.com/LJMoffat81/scot-land/blob/main/docs/mintlify/introduction.mdx";
const MINTLIFY_API =
  "https://github.com/LJMoffat81/scot-land/blob/main/docs/mintlify/api-reference.mdx";

export default function DevelopersPage() {
  const [data, setData] = useState<Downloads | null>(null);
  const [commit, setCommit] = useState<string | null>(null);

  useEffect(() => {
    void apiJson<Downloads>("/downloads")
      .then(setData)
      .catch(() => setData({ items: [] }));
    void apiJson<{ stamp?: { commit?: string } }>("/health")
      .then((body) => setCommit(body.stamp?.commit || null))
      .catch(() => setCommit(null));
  }, []);

  return (
    <main className="downloads-page" data-testid="developers-page">
      <SiteNav current="developers" />
      <h1>Downloads &amp; API</h1>
      <ResearchBanner />
      <p>
        Use Scot-LAND&apos;s open data in your own work. Everything here is free
        under the licence shown. Please say where it came from. Input quality
        tags are{" "}
        <span className="quality-tag-inline" data-testid="quality-tag-inline">
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
      {data?.note && <p className="downloads-note">{data.note}</p>}

      <section id="downloads">
        <h2>Download files</h2>
        <p className="downloads-note">
          Open tables and links behind the map. Until a packaged file exists,
          use the JSON addresses below.
        </p>
        <ul>
          {OPEN_JSON.map((item) => {
            const href = withExportVersion(item.href, commit);
            return (
              <li key={item.href}>
                <a href={href}>{item.name}</a>
                <span className="download-path">{href}</span>
              </li>
            );
          })}
        </ul>

        <h3>Official sources</h3>
        <ul>
          {(data?.items || [])
            .filter((item) => item.url)
            .map((item) => (
              <li key={item.id}>
                <a href={item.url} target="_blank" rel="noreferrer">
                  {SOURCE_NAME[item.id] || item.label}
                </a>
                <span className="download-path">
                  {item.label}
                  {item.licence ? ` · ${item.licence}` : ""}
                  {item.note ? ` — ${item.note}` : ""}
                </span>
              </li>
            ))}
        </ul>
      </section>

      <section id="api">
        <h2>API (for developers)</h2>
        <p>
          Ask for data about one place, or the area on screen. Answers come
          back as JSON. Full reference:{" "}
          <a href="/developers/api">API reference</a>
          {" · "}
          <a href="/developers/checks">Technical checks</a>
          {" · "}
          <a href={MINTLIFY_API} target="_blank" rel="noreferrer">
            docs/mintlify/api-reference.mdx
          </a>
          {" · "}
          <a href={MINTLIFY_INTRO} target="_blank" rel="noreferrer">
            introduction
          </a>
          .
        </p>
        <ul>
          <li>
            One place
            <span className="download-path">
              <a href="/api/place.json?pc=EH1+1YZ">
                GET /api/place.json?pc=EH1+1YZ
              </a>
            </span>
          </li>
          <li>
            Source catalogue
            <span className="download-path">
              <a href="/api/catalog.json">GET /api/catalog.json</a>
            </span>
          </li>
          <li>
            Land rent ledger (structure and rules; no rent figures yet)
            <span className="download-path">
              <a href="/api/ledger.json">GET /api/ledger.json</a>
            </span>
          </li>
        </ul>
      </section>
    </main>
  );
}

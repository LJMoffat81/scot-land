"use client";

import { useEffect, useState } from "react";
import { apiJson, getApiBaseUrl } from "../../lib/api";
import { withExportVersion } from "../../lib/exportUrl";

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

export default function DownloadsPage() {
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
    <main className="downloads-page">
      <p className="downloads-nav">
        <a href="/">Map</a>
        {" · "}
        <a href="/data">Data</a>
        {" · "}
        <a href="/open-api">Public API</a>
        {" · "}
        <a href="/methodology">About</a>
      </p>
      <h1>Downloads</h1>
      <p className="downloads-note" data-testid="experimental-not-official">
        Experimental research only — not an official valuation, rates bill or
        tax assessment. Scot-LAND&apos;s purpose is Annual Ground Rent (the rent
        of land at every place in Scotland). £ figures are not published yet
        while calibration is checked; when they are, each will carry a market,
        proxy or shadow confidence label. For now, figures are published at
        Data Zone level only, not for individual parcels, plots or addresses.
      </p>
      <p>
        These are the open tables and links behind the map: ownership context,
        vacant land, ledger structure and catalogue metadata for the three
        commons inputs (Surface, Resource, Eco). Input quality tags are{" "}
        <code>live</code>, <code>derived</code>, <code>modelled</code> and{" "}
        <code>placeholder</code>; placeholders never appear here. Annual Ground
        Rent amounts are not a public download. Docs:{" "}
        <a href={MINTLIFY_INTRO} target="_blank" rel="noreferrer">
          docs/mintlify/introduction.mdx
        </a>
        {" · "}
        <a href={MINTLIFY_API} target="_blank" rel="noreferrer">
          docs/mintlify/api-reference.mdx
        </a>
        .
      </p>
      {data?.note && <p className="downloads-note">{data.note}</p>}

      <h2>Figures from this site</h2>
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
      <p className="downloads-note">
        A technical description of these addresses is on the{" "}
        <a href={`${getApiBaseUrl()}/docs`}>API docs</a> and in{" "}
        <a href={MINTLIFY_API} target="_blank" rel="noreferrer">
          docs/mintlify
        </a>
        .
      </p>

      <h2>Official sources</h2>
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
    </main>
  );
}

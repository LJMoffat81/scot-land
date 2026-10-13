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
];

const SOURCE_NAME: Record<string, string> = {
  vdl_register: "Scottish Vacant and Derelict Land Survey",
  ldp_allocations: "Local Development Plan allocations (Spatial Hub / OGL)",
  inspire_parcels: "Registers of Scotland open land map",
  common_good: "Common Good registers (linked; no national open map)",
  scotlis: "ScotLIS, the official title record",
};

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
      <p>
        These are the open tables and links behind the map. Modelled Annual
        Ground Rent for councils (including rent per square metre) is not a
        public download — AGR £ stays internal at Data Zone band level until
        yield calibration. The files here are ownership, vacant land, and
        catalogue metadata. They are not a download of every land boundary.
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
        <a href={`${getApiBaseUrl()}/docs`}>API docs</a>.
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

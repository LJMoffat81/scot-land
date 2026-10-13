import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Public API | Scot-LAND",
  description:
    "Open place, ownership and layer addresses that feed Scot-LAND’s Annual Ground Rent map. £ figures not published yet.",
  openGraph: {
    title: "Public API | Scot-LAND",
    description:
      "Open place, ownership and layer addresses that feed Scot-LAND’s Annual Ground Rent map. £ figures not published yet.",
  },
};

export const dynamic = "force-dynamic";

const MINTLIFY_API =
  "https://github.com/LJMoffat81/scot-land/blob/main/docs/mintlify/api-reference.mdx";
const MINTLIFY_INTRO =
  "https://github.com/LJMoffat81/scot-land/blob/main/docs/mintlify/introduction.mdx";

export default function OpenApiPage() {
  return (
    <main className="downloads-page">
      <p className="downloads-nav">
        <a href="/">Map</a>
        {" · "}
        <a href="/data">Data</a>
        {" · "}
        <a href="/downloads">Downloads</a>
        {" · "}
        <a href="/methodology">About</a>
      </p>
      <h1>Public API</h1>
      <p className="downloads-note" data-testid="experimental-not-official">
        Experimental research only — not an official valuation, rates bill or
        tax assessment. Scot-LAND&apos;s purpose is Annual Ground Rent (the rent
        of land at every place in Scotland). £ figures are not published yet
        while calibration is checked; when they are, each will carry a market,
        proxy or shadow confidence label. For now, figures are published at
        Data Zone level only, not for individual parcels, plots or addresses.
      </p>
      <p>
        These addresses return the open place and layer inputs behind the map:
        geography, ownership context and natural-capital ledger structure for
        the three commons (Surface, Resource, Eco). Input quality tags are{" "}
        <code>live</code>, <code>derived</code>, <code>modelled</code> and{" "}
        <code>placeholder</code>; placeholders are never served here. The SG
        2024 public/Crown land dashboard is not an open layer here (licence
        unverified/not open). The answers are for the area in view, or for one
        place. They are not a download of every land boundary. Full reference:{" "}
        <a href={MINTLIFY_API} target="_blank" rel="noreferrer">
          docs/mintlify/api-reference.mdx
        </a>
        ; framing:{" "}
        <a href={MINTLIFY_INTRO} target="_blank" rel="noreferrer">
          docs/mintlify/introduction.mdx
        </a>
        .
      </p>

      <h2>One place</h2>
      <ul>
        <li>
          A short card for one postcode
          <span className="download-path">
            <a href="/api/place.json?pc=EH1+1YZ">
              GET /api/place.json?pc=EH1+1YZ
            </a>
          </span>
        </li>
      </ul>

      <h2>Map layers</h2>
      <ul>
        <li>
          RoS INSPIRE cadastral parcels in view (PostGIS ingest; 503 when not
          loaded)
          <span className="download-path">
            GET /layers/parcels?south=&amp;west=&amp;north=&amp;east=
          </span>
        </li>
        <li>
          Data Zone boundaries in view (2011 outlines; simplified GeoJSON by
          bbox; code and name only)
          <span className="download-path">
            GET /layers/open/data-zones?south=&amp;west=&amp;north=&amp;east=
          </span>
        </li>
        <li>
          Vacant and derelict land in view, site-level from the Scottish
          Vacant and Derelict Land Survey (503 when the overlay source is down)
          <span className="download-path">
            GET /layers/open/vdl?south=&amp;west=&amp;north=&amp;east=
          </span>
        </li>
        <li>
          Housing land audit / supply sites in view, from Spatial Hub OGL
          ingest in PostGIS (503 when unloaded)
          <span className="download-path">
            GET /layers/open/hla?south=&amp;west=&amp;north=&amp;east=
          </span>
        </li>
        <li>
          Community ownership assets in view from the Scottish Government 2024
          OGL dataset (PostGIS postcode centroids; ownership-context; 503 when
          unloaded)
          <span className="download-path">
            GET /layers/open/community-ownership?south=&amp;west=&amp;north=&amp;east=
          </span>
        </li>
        <li>
          Data Zone house prices, SIMD and population density (OGL context;
          ledger frame for row 1; polygons when boundaries are loaded)
          <span className="download-path">
            GET /layers/open/dz-context?vintage=2011
          </span>
        </li>
        <li>
          LDP allocations in view from PostGIS (OGL Spatial Hub / authority
          seeds; 503 when the table is empty; national coverage is fragmented;
          feeds ledger nested row 1a)
          <span className="download-path">
            GET /layers/open/ldp?south=&amp;west=&amp;north=&amp;east=
          </span>
        </li>
        <li>
          NatureScot SSSI in view (OGL PostGIS ingest; 503 when unloaded).
          Constraint overlay — changes best permitted use only; not a commons
          row.
          <span className="download-path">
            GET /layers/open/sssi?south=&amp;west=&amp;north=&amp;east=
          </span>
        </li>
        <li>
          NatureScot SPA / SAC / NNR in view (OGL PostGIS ingest; 503 when
          unloaded). Constraint overlay — changes best permitted use only; not
          a commons row.
          <span className="download-path">
            GET /layers/open/naturescot-designations?south=&amp;west=&amp;north=&amp;east=
          </span>
        </li>
        <li>
          CES aquaculture seabed leases in view (PostGIS; OGL Spatial Hub;
          ledger row 5; attributes and status only; 503 when unloaded)
          <span className="download-path">
            GET /layers/open/ces-aquaculture?south=&amp;west=&amp;north=&amp;east=
          </span>
        </li>
      </ul>

      <h2>Tables</h2>
      <ul>
        <li>
          <a href="/api/vdl.json">
            Vacant and derelict land, from the Scottish Vacant and Derelict
            Land Survey
          </a>
          <span className="download-path">/api/vdl.json</span>
        </li>
        <li>
          <a href="/api/ldp.json">
            LDP allocations — PostGIS coverage and honest national gaps
          </a>
          <span className="download-path">/api/ldp.json</span>
        </li>
        <li>
          <a href="/api/catalog.json">
            What is on the map, what is only linked, and what is missing
          </a>
          <span className="download-path">/api/catalog.json</span>
        </li>
        <li>
          <a href="/api/ledger.json">
            Natural capital ledger — rows 1–10 (+1a), checks, excluded list,
            benchmarks (not inputs); optional zone_id
          </a>
          <span className="download-path">/api/ledger.json</span>
        </li>
        <li>
          <a href="/api/registers.json">Official register pages</a>
          <span className="download-path">/api/registers.json</span>
        </li>
        <li>
          <a href="/api/common-good.json">
            Common Good registers — verified links; no national open map layer
          </a>
          <span className="download-path">/api/common-good.json</span>
        </li>
        <li>
          <a href="/api/crofting.json">
            Crofting Register + common grazings — OGL tables; map extents on RoS
          </a>
          <span className="download-path">/api/crofting.json</span>
        </li>
      </ul>

      <p className="downloads-note">
        Council ownership is not in these files. ScotLIS remains the official
        title record. A technical description is at <code>/docs</code> on the
        API, and in{" "}
        <a href={MINTLIFY_API} target="_blank" rel="noreferrer">
          docs/mintlify
        </a>
        .
      </p>
    </main>
  );
}

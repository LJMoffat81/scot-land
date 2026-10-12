import type { Metadata } from "next";
import { withExportVersion } from "../../lib/exportUrl";

export const metadata: Metadata = {
  title: "Public API | Scot-LAND",
  description:
    "Addresses that return the open Annual Ground Rent figures for one place or the area in view. Research estimate, not a bill.",
  openGraph: {
    title: "Public API | Scot-LAND",
    description:
      "Addresses that return the open Annual Ground Rent figures for one place or the area in view. Research estimate, not a bill.",
  },
};

export const dynamic = "force-dynamic";

async function liveCommit(): Promise<string | null> {
  const base = (
    process.env.API_PROXY_TARGET ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
  try {
    const response = await fetch(`${base}/health`, { cache: "no-store" });
    if (!response.ok) return null;
    const body = (await response.json()) as { stamp?: { commit?: string } };
    return body.stamp?.commit || null;
  } catch {
    return null;
  }
}

export default async function OpenApiPage() {
  const rollCsv = withExportVersion("/api/roll.csv", await liveCommit());
  return (
    <main className="downloads-page">
      <p className="downloads-nav">
        <a href="/">Map</a>
        {" · "}
        <a href="/downloads">Downloads</a>
        {" · "}
        <a href="/methodology">About</a>
      </p>
      <h1>Public API</h1>
      <p>
        These addresses return the open figures behind the map. They are a
        research estimate, not a rates bill. Public and Crown land here is the
        five national bodies, not a title and not council land. The answers are
        for the area in view, or for one place. They are not a download of
        every land boundary.
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
        <li>
          A written assessment you can download
          <span className="download-path">
            GET /assessment/report?lat=&amp;lng=&amp;format=markdown
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
          bbox; code and name only — no AGR £)
          <span className="download-path">
            GET /layers/open/data-zones?south=&amp;west=&amp;north=&amp;east=
          </span>
        </li>
        <li>
          Public and Crown land in view, for the five national bodies (503 when
          the overlay source is down)
          <span className="download-path">
            GET /layers/open/public-land?south=&amp;west=&amp;north=&amp;east=
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
          Annual Ground Rent for each council, as a map file
          <span className="download-path">
            GET /layers/councils?scenario=full_agr
          </span>
        </li>
      </ul>

      <h2>Tables</h2>
      <ul>
        <li>
          <a href="/api/roll.json">Annual Ground Rent for each council</a>
          <span className="download-path">/api/roll.json</span>
        </li>
        <li>
          <a href={rollCsv}>The same figures as a spreadsheet</a>
          <span className="download-path">{rollCsv}</span>
        </li>
        <li>
          <a href="/api/public-land.json">
            Public and Crown land, by the five national bodies
          </a>
          <span className="download-path">/api/public-land.json</span>
        </li>
        <li>
          <a href="/api/vdl.json">
            Vacant and derelict land, from the Scottish Vacant and Derelict
            Land Survey
          </a>
          <span className="download-path">/api/vdl.json</span>
        </li>
        <li>
          <a href="/api/catalog.json">
            What is on the map, what is only linked, and what is missing
          </a>
          <span className="download-path">/api/catalog.json</span>
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
      </ul>

      <p className="downloads-note">
        Council ownership is not in these files. ScotLIS remains the official
        title record. A technical description is at <code>/docs</code> on the
        API.
      </p>
    </main>
  );
}

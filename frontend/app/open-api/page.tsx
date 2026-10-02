export default function OpenApiPage() {
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
        Open JSON for Scot-LAND. Research AGR figures are not a rates
        bill. Public/Crown geometry is a viewport overlay, not a bulk extract.
        Interactive schema: backend <code>/docs</code>.
      </p>

      <h2>Assessment</h2>
      <ul>
        <li>
          <code>GET /square?lat=&amp;lng=</code> — AGR for a W3W cell, with
          ownership place card
        </li>
        <li>
          <code>GET /api/place.json?pc=EH1+1YZ</code> — compact AGR, parcel,
          vacant, public/Crown, register links
        </li>
        <li>
          <code>GET /assessment/report?lat=&amp;lng=&amp;format=markdown</code> —
          downloadable assessment
        </li>
      </ul>

      <h2>Open layers</h2>
      <ul>
        <li>
          <code>GET /layers/open/vdl?south=&amp;west=&amp;north=&amp;east=</code>{" "}
          — SVDLS polygons in view (OGL)
        </li>
        <li>
          <code>
            GET /layers/open/public-land?south=&amp;west=&amp;north=&amp;east=
          </code>{" "}
          — five-body public/Crown polygons in view
        </li>
        <li>
          <code>GET /layers/councils?scenario=full_agr</code> — council AGR
          GeoJSON
        </li>
      </ul>

      <h2>Statistics</h2>
      <ul>
        <li>
          <a href="/api/roll.json">/api/roll.json</a> — 32-council AGR roll +
          vacant ha
        </li>
        <li>
          <a href="/api/roll.csv">/api/roll.csv</a>
        </li>
        <li>
          <a href="/api/public-land.json">/api/public-land.json</a> — hectares by
          body
        </li>
        <li>
          <a href="/api/vdl.json">/api/vdl.json</a> — SVDLS by owner class
        </li>
        <li>
          <a href="/api/catalog.json">/api/catalog.json</a> — live / linked / gap
        </li>
        <li>
          <a href="/api/registers.json">/api/registers.json</a> — official
          landing pages
        </li>
      </ul>

      <p className="downloads-note">
        No portal scraping. Local-authority ownership is a documented gap.
        ScotLIS remains the official title service.
      </p>
    </main>
  );
}

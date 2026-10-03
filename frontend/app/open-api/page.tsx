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
        These addresses return the open figures behind the map. They are a
        research estimate, not a rates bill. Public and Crown land here is the
        five national bodies, not a title and not council land. The answers are
        for the area in view, or for one place. They are not a download of
        every land boundary.
      </p>

      <h2>One place</h2>
      <ul>
        <li>
          The Annual Ground Rent at a point on the map
          <span className="download-path">GET /square?lat=&amp;lng=</span>
        </li>
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
          Vacant and derelict land in view, from the Scottish Vacant and
          Derelict Land Survey
          <span className="download-path">
            GET /layers/open/vdl?south=&amp;west=&amp;north=&amp;east=
          </span>
        </li>
        <li>
          Public and Crown land in view, for the five national bodies
          <span className="download-path">
            GET /layers/open/public-land?south=&amp;west=&amp;north=&amp;east=
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
          <a href="/api/roll.csv">The same figures as a spreadsheet</a>
          <span className="download-path">/api/roll.csv</span>
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
      </ul>

      <p className="downloads-note">
        Council ownership is not in these files. ScotLIS remains the official
        title record. A technical description is at <code>/docs</code> on the
        API.
      </p>
    </main>
  );
}

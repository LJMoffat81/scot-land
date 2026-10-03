export default function MethodologyContent() {
  return (
    <main className="methodology-page">
      <p className="meta" style={{ marginBottom: "0.5rem" }}>
        <a href="/">Map</a>
        {" · "}
        <a href="/downloads">Downloads</a>
        {" · "}
        <a href="/open-api">Public API</a>
      </p>
      <h1>About</h1>
      <p>
        Scot-LAND values one piece of land. The figure is its yearly rental
        value. The building is left out. It is a research estimate, not a rates
        bill and not an official assessment.
      </p>
      <p>
        Two pieces of the same size in the same council get the same rent. The
        rate is that council&apos;s, so it does not change from one street to
        the next.
      </p>
      <p>
        <a href="#calculation">How a place is valued</a>
        {" · "}
        <a href="#why">Why I am building this</a>
      </p>

      <section id="calculation">
        <h2>How a place is valued</h2>
        <p>
          In a town council, the rent is that council&apos;s land rent for each
          square metre, times the area of this piece. The land rent is what
          remains after the building and the speculative part are taken off,
          and a 5% yield is applied. In a rural council the rate is the
          farmland rate, and the map colour is one hectare of that farmland.
          A click shows the piece of land itself.
        </p>
      </section>

      <section id="why">
        <h2>Why I am building this</h2>
        <p>I am Laurie Moffat. I am building Scot-LAND because there is not a tool for this.</p>
        <p>
          The catalyst was a run of official reports on how land is valued for
          tax. They do not endorse this site. They name the gap that has stalled
          the policy.
        </p>
        <p>
          In October 2025 the Scottish Land Commission published{" "}
          <a
            href="https://www.landcommission.gov.scot/downloads/68f737cad6890_Approaches-to-land-valuation-in-the-tax-system.pdf"
            target="_blank"
            rel="noreferrer"
          >
            Approaches to land valuation in the tax system
          </a>
          . Its comparison finds that a Scottish home is still valued on 1991
          bands, that those bands include the building, and that the system
          ignores a valuation of the land alone.{" "}
          <a
            href="https://www.landcommission.gov.scot/news-events/news/global-lessons-could-help-scotland-build-a-fairer-greener-land-tax-system"
            target="_blank"
            rel="noreferrer"
          >
            Publishing the report
          </a>
          , the Commission said Scotland has no national process for revaluing
          homes, and no single database joining the map, the register, and
          sales.
        </p>
        <p>
          In March 2026 its paper{" "}
          <a
            href="https://www.landcommission.gov.scot/next-steps-for-land-reform/4-delivery-co-ordinated-use-of-policy-tax-and-fiscal-levers"
            target="_blank"
            rel="noreferrer"
          >
            Next steps for land reform
          </a>{" "}
          said there is not currently enough data on land use, value and
          ownership for Scotland to use its tax powers in a transformative way.
          It said Scotland falls behind other countries in gathering land data
          for tax decisions. The same paper records public interest in land
          value taxation. It does not set a rate.
        </p>
        <p>
          In August 2026 its{" "}
          <a
            href="https://www.landcommission.gov.scot/a-five-year-route-to-modernising-land-tax-administration/the-case-for-modernising-land-tax-administration"
            target="_blank"
            rel="noreferrer"
          >
            five-year route to modernising land tax administration
          </a>{" "}
          said Scotland does not have an up-to-date or complete picture of land
          value, and that these practical hurdles are regularly identified in
          debates about land value taxation.
        </p>
        <p>
          This map is my answer to that gap. A person can look at one piece of
          land and see a research estimate of its Annual Ground Rent. The
          building stays with the person who made it. The figure is not a rates
          bill, and it is not an official assessment.
        </p>
        <h3>Contact</h3>
        <p>
          <a href="mailto:laurie.moffat@scot-land.scot">
            laurie.moffat@scot-land.scot
          </a>
          <br />
          <a href="https://x.com/LJMoffat81" target="_blank" rel="noreferrer">
            X: @LJMoffat81
          </a>
          <br />
          <a href="https://github.com/LJMoffat81" target="_blank" rel="noreferrer">
            GitHub: LJMoffat81
          </a>
        </p>
      </section>

      <p className="meta">
        The mark uses the &ldquo;Land&rdquo; icon by Adrien Coquet, from{" "}
        <a href="https://thenounproject.com/browse/icons/term/land/">Noun Project</a>{" "}
        (CC BY 3.0).
      </p>
      <p>
        <a href="/">Back to map</a>
      </p>
    </main>
  );
}

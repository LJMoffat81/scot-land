export default function MethodologyContent() {
  return (
    <main className="methodology-page">
      <p className="meta" style={{ marginBottom: "0.5rem" }}>
        <a href="/">Map</a>
        {" · "}
        <a href="/data">Data</a>
        {" · "}
        <a href="/downloads">Downloads</a>
        {" · "}
        <a href="/open-api">Public API</a>
      </p>
      <h1>About</h1>
      <p>
        Scot-LAND estimates an Annual Ground Rent for land across Scotland: what
        the land alone would be worth to use each year, leaving out any
        buildings on it.
      </p>
      <p>
        It&apos;s a research estimate, not a rates bill. Nobody owes this amount, and
        it isn&apos;t a proposal for what anyone should pay.
      </p>
      <p>
        A click on land estimates the surface rent. A click at sea says the
        seabed is land, and names a Crown Estate Scotland lease when one covers
        that point. The note is the published rent rule. Where the open file
        has no yearly total, the map does not invent one. Minerals and water
        are not on the map yet, and woodland shows &quot;Not yet estimated&quot;.
      </p>
      <p>
        Figures come from public data, and the method is published in full.
        They&apos;re in development and may change as the work improves, and
        each result shows the version it came from.
      </p>
      <p>
        We never show who owns land, what it sold for, or title plans.
      </p>
      <p>
        Where a register outline exists, the figure is that piece of land. Where it does not, a town click is one home plot and a countryside click is one hectare of farmland.
      </p>
      <p>
        <a href="#calculation">How a place is valued</a>
        {" · "}
        <a href="#why">Why I am building this</a>
      </p>

      <section id="calculation">
        <h2>How a place is valued</h2>
        <p>
          Each point on land is classed as town or countryside. In a town, the
          rent is that council&apos;s land rent for each square metre, times the
          area of this piece. The land rent is what remains after the building
          and the speculative part are taken off, and a 5% yield is applied.
          In the countryside the rate is one farmland rate for Scotland, times
          the area. The map colour is one town home-plot rate for each council.
          A click can differ from that colour when the point is countryside, or
          when the outline is not a home plot.
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

      <section id="what-is-agr">
        <h2>What is Annual Ground Rent?</h2>
        <p>
          Where the land register shows an outline, it is that piece of land. In a town with no outline, it is one home&apos;s land rent from that neighbourhood&apos;s house price. In the countryside with no outline, it is one farmland rate for one hectare. The building is not included.
        </p>
      </section>

      <section id="how-sure">
        <h2>How sure are these numbers?</h2>
        <p>
          They&apos;re research estimates, and some of what goes into them can&apos;t be pinned down exactly. With different reasonable assumptions, the estimate for a typical home plot in most councils could be anywhere from about half to 1.3 times the figure shown. Where house prices are low compared with what homes cost to rebuild, the range is wider, from about half to about double. This range covers home plots only, not the farmland figures. It does not cover the bigger simplifications. The map colour is still one town rate for a whole council. A click follows town or countryside at that point, and where an outline exists the number is that piece of land, not the home plot. A town click uses that data zone&apos;s median house price, which is still the price of an improved dwelling. A larger piece of land follows a diminishing area rule. The council median stays the comparison and the fallback. In most councils, the home-plot figures are slightly more likely to be too high than too low.
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

const MINTLIFY = {
  introduction:
    "https://github.com/LJMoffat81/scot-land/blob/main/docs/mintlify/introduction.mdx",
  mapLayers:
    "https://github.com/LJMoffat81/scot-land/blob/main/docs/mintlify/map-layer-guide.mdx",
  apiReference:
    "https://github.com/LJMoffat81/scot-land/blob/main/docs/mintlify/api-reference.mdx",
};

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
        Scot-LAND is an experimental, non-commercial research map of Scotland&apos;s
        commons. It is building an open land information platform so people can
        see where value from land and natural resources sits — not as a rates
        bill, and not as an official valuation or tax assessment.
      </p>
      <p className="downloads-note" data-testid="experimental-not-official">
        Experimental research only. Figures on this site are not official
        valuations, rates bills or tax assessments. Modelled money amounts for
        land and resource value are not published on the public map or downloads
        until the commons engine passes review.
      </p>
      <p>
        A click on the public map opens a place card for location and open
        layers. A click at sea can name a Crown Estate Scotland lease when one
        covers that point. Method depth lives in the{" "}
        <a href={MINTLIFY.introduction} target="_blank" rel="noreferrer">
          Mintlify introduction
        </a>
        ,{" "}
        <a href={MINTLIFY.mapLayers} target="_blank" rel="noreferrer">
          map layer guide
        </a>
        , and{" "}
        <a href={MINTLIFY.apiReference} target="_blank" rel="noreferrer">
          API reference
        </a>{" "}
        under <code>docs/mintlify</code>.
      </p>
      <p>
        We never show who owns private land, what it sold for, or title plans.
      </p>
      <p>
        <a href="#commons">The three commons</a>
        {" · "}
        <a href="#quality">Quality tags</a>
        {" · "}
        <a href="#why">Why I am building this</a>
      </p>

      <section id="commons">
        <h2>The three commons</h2>
        <p>
          The commons engine splits value into three separate classes so they are
          never mixed into one headline number:
        </p>
        <ul>
          <li>
            <strong>Surface (location)</strong> — value from where land sits:
            access, amenity, agglomeration and permitted use (homes, business,
            farm and forestry; idle and allocated sites).
          </li>
          <li>
            <strong>Resource (extractive)</strong> — value from depletable or
            licensed natural resources, net of extraction cost (for example
            seabed leases, minerals, water abstraction).
          </li>
          <li>
            <strong>Eco (sinks and services)</strong> — value of natural systems
            that absorb harm or provide services (for example peatland and
            woodland carbon, flood regulation).
          </li>
        </ul>
        <p>
          Each class is also tagged as market, proxy or shadow so different
          kinds of evidence are not added together. Constraint overlays
          (designations, flood, crofting and similar) change best permitted use
          only; they are not a commons row. Full rules:{" "}
          <a href={MINTLIFY.introduction} target="_blank" rel="noreferrer">
            docs/mintlify/introduction.mdx
          </a>
          .
        </p>
      </section>

      <section id="quality">
        <h2>Quality tags</h2>
        <p>
          Every figure the engine holds carries a data-state quality tag. The
          public site only exposes layers that are ready; placeholders stay off
          public routes.
        </p>
        <ul>
          <li>
            <strong>live</strong> — observed from a public source as-is.
          </li>
          <li>
            <strong>derived</strong> — computed from open inputs by a stated
            method.
          </li>
          <li>
            <strong>modelled</strong> — estimated by the residual / mass model;
            not published as public money figures until review.
          </li>
          <li>
            <strong>placeholder</strong> — not ready; never served on the public
            API or map.
          </li>
        </ul>
        <p>
          Missing data is shown as a gap (HTTP 503), never filled with a
          placeholder. See the{" "}
          <a href={MINTLIFY.apiReference} target="_blank" rel="noreferrer">
            Mintlify API reference
          </a>
          .
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
          This map is my answer to that gap: an open commons ledger for Scotland
          — surface, resource and eco kept separate, quality-tagged, and honest
          about what is still experimental. It is not a rates bill, and it is
          not an official assessment.
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

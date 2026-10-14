import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";

export default function MissionContent() {
  return (
    <main className="methodology-page" data-testid="mission-page">
      <SiteNav current="about" />
      <h1>About Scot-LAND</h1>
      <ResearchBanner />

      <section id="why">
        <h2>Why I am building this</h2>
        <p>
          Scotland&apos;s land and natural resources are worth a great deal, but
          few people can see that value or who holds it. Debates about land
          reform and land value tax should rest on shared, honest evidence, not
          guesswork.
        </p>
      </section>

      <section id="goal">
        <h2>Goal</h2>
        <p>
          Scot-LAND&apos;s purpose is to show{" "}
          <strong>Annual Ground Rent</strong> — the yearly rental value of the
          land itself, not the buildings — for every place in Scotland, and who
          holds it. The map covers surface land and natural-resource rents such
          as wind, fish farming, hydro, forestry and peat carbon. A later module
          values nature itself.
        </p>
        <p>
          Open data only at launch; paid sources may be added later, each
          clearly tagged; paid data never republished.
        </p>
      </section>

      <section id="who">
        <h2>Who it&apos;s for</h2>
        <p>
          The public, researchers, journalists, policy makers and community
          groups who want to understand Scottish land.
        </p>
      </section>

      <section id="what-it-isnt">
        <h2>What it isn&apos;t</h2>
        <ul>
          <li>
            Not an official valuation or bill — every estimate is a research
            estimate; figures pending sign-off.
          </li>
          <li>
            Owner details come from public records only. Private names beyond
            those records are not shown.
          </li>
          <li>
            Open data only at launch; paid sources may be added later, each
            clearly tagged; paid data never republished. A what3words lookup
            stays a switched-off future adapter. The grid is called a{" "}
            <strong>Scot-LAND square reference</strong>, not what3words.
          </li>
          <li>
            For now, figures are published at Data Zone level only, not for
            individual parcels, plots or addresses.
          </li>
        </ul>
      </section>

      <section id="done">
        <h2>What done looks like</h2>
        <ul>
          <li>
            Annual Ground Rent figures published for every area of Scotland,
            once the economic rules behind them are approved — shown only as
            ranges labelled market, proxy or shadow.
          </li>
          <li>Natural-resource rent layers live on the map.</li>
          <li>Every layer has passed source and licence checks.</li>
          <li>
            Every value can be traced to a data zone and an open source, using
            the Scottish Government roll-up (see{" "}
            <a href="/methodology">How it works</a>).
          </li>
        </ul>
      </section>

      <section id="get-involved">
        <h2>Get involved</h2>
        <p>
          Read <a href="/methodology">How it works</a>, explore open{" "}
          <a href="/data">Data &amp; sources</a>, or use{" "}
          <a href="/developers">Downloads &amp; API</a>. Feedback and
          corrections welcome.
        </p>
        <p>
          <a href="mailto:laurie.moffat@scot-land.scot">
            laurie.moffat@scot-land.scot
          </a>
          <br />
          <a href="https://x.com/LJMoffat81" target="_blank" rel="noreferrer">
            X: @LJMoffat81
          </a>
          <br />
          <a
            href="https://github.com/LJMoffat81/scot-land"
            target="_blank"
            rel="noreferrer"
          >
            GitHub: LJMoffat81/scot-land
          </a>
        </p>
      </section>

      <p className="meta">
        The mark uses the &ldquo;Land&rdquo; icon by Adrien Coquet, from{" "}
        <a href="https://thenounproject.com/browse/icons/term/land/">
          Noun Project
        </a>{" "}
        (CC BY 3.0).
      </p>
      <p>
        <a href="/">Back to map</a>
        {" · "}
        <a href="/methodology">How it works</a>
      </p>
    </main>
  );
}

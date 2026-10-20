import ContentPageFooter from "@/components/ContentPageFooter";
import GbpLiveBannerNote from "@/components/GbpLiveBannerNote";
import GlossaryBox from "@/components/GlossaryBox";
import HashRedirect from "@/components/HashRedirect";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { AREA_LEVELS, AREA_LEVELS_EXPLANATION } from "@/lib/areaLevels";

/**
 * How it works page copy — SLRG wording (site-watch PR C / SW-017).
 * GBP-LIVE £ copy mounts only when the backend flag is on (client note).
 */
export default function MethodologyContent() {
  return (
    <main className="methodology-page" data-testid="methodology-page">
      <HashRedirect fromHash="why" to="/about#why" />
      <SiteNav current="how" />
      <h1>How it works</h1>
      <ResearchBanner variant="methodology" />
      <GbpLiveBannerNote />

      <p data-testid="methodology-agr-definition">
        <strong>What is Annual Ground Rent?</strong>
        {" "}
        It is the yearly rental value of a site, the land without its buildings.
        Buildings are left out, because whoever built them made that value. The land&apos;s value is
        created by the community around it and by nature, not by the owner.
      </p>
      <p>
        We show figures for Data Zones for now. Our aim is to value each piece
        of land by the square metre, year by year, built up step by step from
        accurate public data.
      </p>

      <section id="calculation">
        <h2>How an area is valued</h2>
        <ul>
          <li>
            In towns, we start from local house prices. We take away what it
            would cost to rebuild the house. What is left is roughly the value
            of the land. We turn that into a yearly rent.
          </li>
          <li>
            <strong>In the countryside</strong>, we use one farmland rent for
            each square metre of land, the same across Scotland.
          </li>
          <li>
            <strong>Natural resource rents and the services of nature</strong>{" "}
            are part of Annual Ground Rent, shown as separate parts; parts with
            different labels are never added into one total.
          </li>
          <li>
            <strong>Limits on use</strong> (nature sites, flood risk, crofting)
            follow the rule{" "}
            <em>Constraint: changes best use, adds no value</em>.
          </li>
        </ul>
      </section>

      <section id="rollup">
        <h2>Small areas, added up honestly</h2>
        <p>
          Every figure belongs to a Data Zone. Data Zones fit inside council areas,
          and council areas make up Scotland. This is the Scottish
          Government&apos;s own system. We add up each kind of figure (Market,
          Modelled, Estimate) separately, and never across different price years.
          Nothing is counted twice.
        </p>
        <p className="downloads-note">
          We show each small area on its own. We don&apos;t add areas up into
          council or Scotland figures.
        </p>
        <p data-testid="methodology-levels-note">{AREA_LEVELS_EXPLANATION}</p>
        <ol data-testid="methodology-levels">
          {AREA_LEVELS.map((level) => (
            <li key={level}>{level}</li>
          ))}
        </ol>
      </section>

      <GlossaryBox title="Words we use" />

      <section id="how-sure">
        <h2>How sure are these numbers?</h2>
        <p>
          They are estimates, and some inputs can&apos;t be pinned down exactly.
          With other sensible assumptions, a Data Zone rent range in most
          councils could be anywhere from about half to 1.3 times our central
          estimate. Where house prices are low compared with rebuild costs, the
          range is wider: about half to double. This covers home Data Zones, not
          farmland, and never a single-property figure. Figures go through a
          separate checking step before anything is published. That step is
          part of the Scot-LAND model, not an outside review.
        </p>
      </section>

      <section id="gaps">
        <h2>What&apos;s missing</h2>
        <p>
          Old land records not yet digital; private owners (we never show them);
          natural-resource figures not yet split by Data Zone; Edinburgh&apos;s
          planning allocations; national common grazings boundaries. Full list:{" "}
          <a href="/data#gaps">Data &amp; sources</a>.
        </p>
      </section>

      <section id="credits">
        <h2>Credits</h2>
        <ul>
          <li>
            Contains OS data © Crown copyright and database right 2026
          </li>
          <li>
            National Records of Scotland: © Crown copyright 2026, licensed under the Open Government Licence v3.0
          </li>
          <li>
            Contains Scottish Government data licensed under the Open Government
            Licence v3.0
          </li>
        </ul>
      </section>

      <p>
        <a href="/">Back to map</a>
        {" · "}
        <a href="/about">About</a>
        {" · "}
        <a href="/data">Data &amp; sources</a>
      </p>
      <ContentPageFooter />
    </main>
  );
}

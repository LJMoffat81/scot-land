import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";

const SLC_APPROACHES =
  "https://www.landcommission.gov.scot/downloads/68f737cad6890_Approaches-to-land-valuation-in-the-tax-system.pdf";
const SLC_NEWS =
  "https://www.landcommission.gov.scot/news-events/news/global-lessons-could-help-scotland-build-a-fairer-greener-land-tax-system";
const SLC_NEXT_STEPS =
  "https://www.landcommission.gov.scot/next-steps-for-land-reform/4-delivery-co-ordinated-use-of-policy-tax-and-fiscal-levers";
const SLC_FIVE_YEAR =
  "https://www.landcommission.gov.scot/a-five-year-route-to-modernising-land-tax-administration/the-case-for-modernising-land-tax-administration";

/**
 * About page copy — site rewrite section B (wording pending Laurie approval).
 */
export default function MissionContent() {
  return (
    <main className="methodology-page" data-testid="mission-page">
      <SiteNav current="about" />
      <h1>About Scot-LAND</h1>
      <ResearchBanner />

      <p>
        Scot-LAND is a free, open map of Scotland&apos;s land. It shows what the
        land itself is worth to use each year, and where that value comes from:
        homes and businesses, farms, wind, water, fish farms, forests and peat.
        Anyone can use it: the public, community groups, journalists,
        researchers and people who make policy.
      </p>

      <section id="what-it-isnt">
        <h2>What Scot-LAND is not</h2>
        <p>
          It is not a bill. It is not a tax proposal. It is not an official
          valuation. We only show owners from public records, never private
          owners&apos; names, sale prices or title plans. We use open data only
          at launch. Paid sources may be added later as the project advances,
          each one clearly tagged. Paid data is never republished or offered for
          download.
        </p>
      </section>

      <section id="why">
        <h2>Why I am building this</h2>
        <p>I am Laurie Moffat. I am building Scot-LAND because there is no tool like it.</p>
        <p>
          The spark was a run of official reports on how land is valued for tax.
          They do not endorse this site, but they name the gap that has held
          policy back.
        </p>
        <ul>
          <li>
            In <strong>October 2025</strong> the Scottish Land Commission
            published{" "}
            <a href={SLC_APPROACHES} target="_blank" rel="noreferrer">
              Approaches to land valuation in the tax system
            </a>
            . It found that Scottish homes are still valued on 1991 bands, that
            those bands include the building, and that the land alone is never
            valued.{" "}
            <a href={SLC_NEWS} target="_blank" rel="noreferrer">
              Publishing the report
            </a>
            , the Commission said Scotland has no national way to revalue homes,
            and no single database joining the map, the register and sales.
          </li>
          <li>
            In <strong>March 2026</strong> its paper{" "}
            <a href={SLC_NEXT_STEPS} target="_blank" rel="noreferrer">
              Next steps for land reform
            </a>{" "}
            said Scotland does not have enough data on land use, value and
            ownership to use its tax powers in a transformative way, and falls
            behind other countries in gathering it. It noted public interest in
            land value tax but did not set a rate.
          </li>
          <li>
            In <strong>August 2026</strong> its{" "}
            <a href={SLC_FIVE_YEAR} target="_blank" rel="noreferrer">
              five-year route to modernising land tax administration
            </a>{" "}
            said Scotland lacks an up-to-date, complete picture of land value, a
            hurdle that comes up again and again in debates on land value tax.
          </li>
        </ul>
        <p>
          This map is my answer to that gap. You can look at any area and see a
          research estimate of what its land is worth to use. The building stays
          with whoever made it. The figure is not a bill and not an official
          assessment.
        </p>
      </section>

      <section id="contact">
        <h2>Contact</h2>
        <p>
          Email{" "}
          <a href="mailto:laurie.moffat@scot-land.scot">
            laurie.moffat@scot-land.scot
          </a>
          {" · "}
          X{" "}
          <a href="https://x.com/LJMoffat81" target="_blank" rel="noreferrer">
            @LJMoffat81
          </a>
          {" · "}
          GitHub{" "}
          <a
            href="https://github.com/LJMoffat81"
            target="_blank"
            rel="noreferrer"
          >
            LJMoffat81
          </a>
        </p>
      </section>

      <p className="meta">
        Credit: the logo uses the &ldquo;Land&rdquo; icon by Adrien Coquet, from{" "}
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

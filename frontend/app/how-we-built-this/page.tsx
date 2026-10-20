import type { Metadata } from "next";
import ContentPageFooter from "@/components/ContentPageFooter";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { contactFormEnabled } from "@/lib/contactFormFlag";
import { OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "How we built this | Scot-LAND",
  description:
    "Who leads Scot-LAND, and how the research, checks and code are done. Research estimate — figures are not published yet.",
  openGraph: {
    title: "How we built this | Scot-LAND",
    description:
      "Who leads Scot-LAND, and how the research, checks and code are done. Research estimate — figures are not published yet.",
    images: [...OG_IMAGES],
  },
};

const ROLES = [
  "Engineering Lead: runs the building work, writes specs and reviews code.",
  "Wording & UX Reviewer: keeps every page clear and easy to use.",
  "Georgist Economist: keeps the work true to land value principles.",
  "Land Value Econometrician: models land values from sales and building costs, and tests how well the model fits.",
  "GIS & Open Data: finds public data, checks its licence and joins it to areas.",
  "Test Engineer: writes the automated tests that guard every change.",
  "Live Site Checker: tests the live site after every change.",
  "Outside Comms: drafts outside messages, which are only sent once a person approves them.",
  "Methods Auditor: checks each method is sound and written down before it is used.",
  "Property Tax & Land Law: checks the work against tax and land law.",
  "Visual Designer: looks after the look of the site and maps.",
  "Project Lead: plans the work and holds it to our rules.",
] as const;

const GAPS = [
  "No qualified valuer has reviewed our method.",
  "Values cover land as it is used today, not what planning might allow.",
  "No legal or data-protection review yet.",
  'No public-finance expert has reviewed our "Why land value?" page.',
  "Rural land is not valued yet.",
  "No independent review of our statistics.",
] as const;

const REVIEWERS = [
  "a RICS-registered valuer, to check how we value land",
  "a statistician, to test our model",
  "a planner, to advise on planning use",
  "a legal or data-protection reviewer",
  "a public-finance economist, to review our tax explainer",
] as const;

export default function HowWeBuiltThisPage() {
  return (
    <main className="methodology-page" data-testid="how-we-built-page">
      <SiteNav current="built" />
      <h1>How we built this</h1>
      <ResearchBanner />
      <div data-testid="how-we-built-copy">
        <div data-testid="how-we-built-intro">
          <p>Scot-LAND is led by Laurie Moffat, an independent volunteer.</p>
          <p>The map runs on the Scotland National Wealth Engine, which we are building step by step.</p>
          <p>The research and checking are done by a team of specialist AI assistants. Each has one job:</p>
        </div>
        <ul data-testid="how-we-built-roles">
          {ROLES.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p>
          These are AI assistants, not people, and they hold no professional qualifications. The code is written by Cursor, an AI coding tool.
        </p>
        <section id="how-we-keep-it-honest">
          <h2>How we keep it honest</h2>
          <ul>
            <li>
              Every method is written down before we use it, checked, and published on{" "}
              <a href="/methodology">How it works</a>.
            </li>
            <li>
              Every dataset is public, and every source is credited on{" "}
              <a href="/data">Data & sources</a>.
            </li>
            <li>
              Every figure is an estimate, shown with a range and a label saying how reliable it is.
            </li>
          </ul>
        </section>
        <section id="what-we-dont-have-yet">
          <h2>What we don&apos;t have yet</h2>
          <ul data-testid="how-we-built-gaps">
            {GAPS.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p>Automated values need human checking before anyone relies on them.</p>
        </section>
        <section id="get-involved">
          <h2>Get involved</h2>
          <p>We would welcome volunteer reviewers:</p>
          <ul data-testid="how-we-built-reviewers">
            {REVIEWERS.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p>This is unpaid and voluntary.</p>
          {contactFormEnabled() ? (
            <p>
              If you spot a mistake or can help, please{" "}
              <a href="/about#contact">get in touch</a>.
            </p>
          ) : null}
        </section>
      </div>
      <ContentPageFooter />
    </main>
  );
}

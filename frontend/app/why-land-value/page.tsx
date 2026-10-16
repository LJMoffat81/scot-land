import type { Metadata } from "next";
import ContentPageFooter from "@/components/ContentPageFooter";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "Why land value?",
  description:
    "Why a charge on the yearly rental value of land is different from taxes on work and spending. This page explains an idea.",
  openGraph: {
    title: "Why land value?",
    description:
      "Why a charge on the yearly rental value of land is different from taxes on work and spending. This page explains an idea.",
    images: [...OG_IMAGES],
  },
};

export default function WhyLandValuePage() {
  return (
    <main className="methodology-page" data-testid="why-land-value-page">
      <SiteNav />
      <h1>Why land value?</h1>
      <ResearchBanner />
      <div data-testid="why-land-value-copy">
        <p>
          This page explains an idea. It is not a policy promise, and it is not
          the position of any political party.
        </p>
        <section>
          <h2>How we tax today</h2>
          <p>
            Most of the money Scotland raises comes from taxes on work, wages,
            spending and business. These taxes can discourage the things we
            want more of: jobs, investment and new homes.
          </p>
        </section>
        <section>
          <h2>Who makes land valuable?</h2>
          <p>
            Land is worth more near jobs, transport, schools and shops. That
            value is created by the whole community and by public spending, not
            by the person who owns the land.
          </p>
        </section>
        <section>
          <h2>A gradual shift</h2>
          <p>
            A charge on the yearly rental value of land could, over time, let
            other taxes come down. It would be phased in slowly. People on low
            incomes could defer it until a home is sold or passed on.
          </p>
        </section>
        <section>
          <h2>See it for yourself</h2>
          <p>
            Our <a href="/">map</a> shows early estimates for each Data Zone in
            Scotland, and our <a href="/roadmap">roadmap</a> shows what comes
            next.
          </p>
        </section>
      </div>
      <ContentPageFooter />
    </main>
  );
}

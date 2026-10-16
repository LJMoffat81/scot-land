import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";

/**
 * API-TEASER-1 — public page is a short coming-soon note.
 * Endpoint and catalogue docs are not shown here.
 */
export default function ApiTeaserPage() {
  return (
    <main className="downloads-page developers-page" data-testid="api-teaser">
      <SiteNav current="developers" />
      <h1>Developer API and bulk data: coming</h1>
      <ResearchBanner />
      <p>The API and bulk data will come from the Scotland National Wealth Engine.</p>
      <p>We plan to offer a developer API and bulk downloads. They will cover:</p>
      <ul>
        <li>
          Land rent estimates for each Data Zone, with ranges and quality labels
        </li>
        <li>Map layers we use, where licences allow</li>
        <li>Sources and method notes for every figure</li>
      </ul>
      <p>The map stays free to use.</p>
      <p>
        <a href="/about#contact" data-testid="api-register-interest">
          Register interest
        </a>
      </p>
    </main>
  );
}

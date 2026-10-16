import type { Metadata } from "next";
import ContentPageFooter from "@/components/ContentPageFooter";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { absoluteOgImageUrl, OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "Roadmap | Scot-LAND",
  description:
    "What is coming to the Scot-LAND map next. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "Roadmap | Scot-LAND",
    description:
      "What is coming to the Scot-LAND map next. Research estimate — land rent figures are not published yet.",
    images: [...OG_IMAGES],
  },
  twitter: {
    card: "summary_large_image",
    title: "Roadmap | Scot-LAND",
    description:
      "What is coming to the Scot-LAND map next. Research estimate — land rent figures are not published yet.",
    images: [absoluteOgImageUrl()],
  },
};

const COMING_TO_THE_MAP: ReadonlyArray<{
  name: string;
  status: string;
}> = [
  {
    name: "Landscape character areas",
    status: "Waiting for permission — licence check",
  },
  {
    name: "Fish and shellfish farms",
    status: "Being checked — source unreliable",
  },
  {
    name: "Natural resource rents",
    status: "Not started",
  },
  {
    name: "Services of nature",
    status: "Not started",
  },
  {
    name: "Full breakdown by part",
    status: "Not started",
  },
  {
    name: "Business land",
    status: "Not started",
  },
  {
    name: "Public land owned by the Crown",
    status: "Not started",
  },
];

export default function RoadmapPage() {
  return (
    <main className="methodology-page" data-testid="roadmap-page">
      <SiteNav />
      <h1>Roadmap</h1>
      <ResearchBanner />

      <section id="map-layers" data-testid="roadmap-map-layers">
        <h2>Coming to the map</h2>
        <p>
          These layers aren&apos;t on the map yet. We add them when the data is
          checked and we&apos;re allowed to show it.
        </p>
        <ul className="roadmap-layer-list">
          {COMING_TO_THE_MAP.map((row) => (
            <li key={row.name} data-testid="roadmap-layer-row">
              <span className="roadmap-layer-name">{row.name}</span>
              <span className="roadmap-layer-status">{row.status}</span>
            </li>
          ))}
        </ul>
      </section>

      <div className="content-page-footer-wrap">
        <ContentPageFooter />
      </div>
    </main>
  );
}

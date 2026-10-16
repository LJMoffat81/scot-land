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
  id?: string;
  name: string;
  blurb?: string;
  status: string;
  statusShort?: string;
}> = [
  // LAYERS-ADD-1a — flagged OFF (PSGA). Exact visitor strings from design L11.
  {
    id: "ldp",
    name: "Planned development land",
    blurb: "Land councils have set aside for building",
    status: "Waiting for permission to use the data",
    statusShort: "Waiting for permission",
  },
  {
    id: "hls",
    name: "Land for new homes",
    blurb: "Sites a council expects to be built for homes",
    status: "Waiting for permission to use the data",
    statusShort: "Waiting for permission",
  },
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
            <li
              key={row.id ?? row.name}
              data-testid={
                row.id ? `roadmap-waiting-${row.id}` : "roadmap-layer-row"
              }
            >
              <span className="roadmap-layer-name">{row.name}</span>
              {row.blurb ? (
                <span className="roadmap-layer-blurb">{row.blurb}</span>
              ) : null}
              <span
                className="roadmap-layer-status"
                data-testid={
                  row.id ? `roadmap-waiting-status-${row.id}` : undefined
                }
              >
                <span className="roadmap-waiting-status-full">{row.status}</span>
                {row.statusShort ? (
                  <span className="roadmap-waiting-status-short">
                    {row.statusShort}
                  </span>
                ) : null}
              </span>
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

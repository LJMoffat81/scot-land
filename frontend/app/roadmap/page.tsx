import type { Metadata } from "next";
import ContentPageFooter from "@/components/ContentPageFooter";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { AIM_TO_COVER } from "@/lib/aimToCover";
import { LAYERS_ADD_WAITING } from "@/lib/layersAddRegistry";
import { MAP_LAYER_REGISTRY } from "@/lib/mapLayerRegistry";
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
  // LDP / HLS status comes from LAYERS_ADD_WAITING (the catalog copy).
  ...LAYERS_ADD_WAITING.map((row) => ({
    id: row.id,
    name: row.title,
    blurb: row.blurb,
    status: row.status,
    statusShort: row.statusShort,
  })),
  ...MAP_LAYER_REGISTRY.filter((entry) => entry.coming).map((entry) => ({
    id: entry.id,
    name: entry.label,
    status: entry.id === "vdl" ? "In progress" : "Not started",
  })),
  {
    name: "Landscape character areas",
    status: "Waiting for permission to use the data",
  },
  {
    name: "Fish and shellfish farms",
    status: "Being checked: the data has gaps",
  },
  {
    name: "Public land owned by the Crown",
    status: "Not started",
  },
];

const OUR_VISION_HEADING = "Our vision";

const OUR_VISION_TEXT =
  "Our long-term aim is to give every piece of land in Scotland its own Annual Ground Rent value, per square metre. Today we show estimates for small areas, called Data Zones. Next we plan to work at the level of individual land parcels, and then on a fine 3-metre grid. We are building this step by step from accurate, publicly available data. Getting it right will take time, and we will keep refining it until it is accurate enough to be a trusted source of land value information for Scotland.";

const OUR_VISION_TODAY = "Today the map shows estimates for Data Zones only.";

const SUGGEST_LAYER_COPY =
  "Know a dataset that would make this map better? Tell us what the layer is, where the data comes from (a link), and why it matters for land value. We check every suggestion against its licence and our method before adding it.";

const SUGGEST_LAYER_HREF =
  "https://github.com/LJMoffat81/scot-land/issues/new?template=suggest-layer.yml";

export default function RoadmapPage() {
  return (
    <main className="methodology-page" data-testid="roadmap-page">
      <SiteNav />
      <h1>Roadmap</h1>
      <ResearchBanner />

      <section id="our-vision" data-testid="roadmap-vision">
        <h2>{OUR_VISION_HEADING}</h2>
        <p>{OUR_VISION_TEXT}</p>
        <p>
          {OUR_VISION_TODAY} <a href="/">Back to map</a>
        </p>
      </section>

      <section id="what-we-aim-to-cover" data-testid="roadmap-aim">
        <h2>What we aim to cover</h2>
        {AIM_TO_COVER.map((group) => (
          <div key={group.id} data-testid={`roadmap-aim-group-${group.id}`}>
            <h3>{group.heading}</h3>
            <ul className="roadmap-layer-list">
              {group.rows.map((row) => (
                <li key={row.id} id={row.id} data-testid="roadmap-aim-row">
                  <span className="roadmap-layer-name">{row.name}</span>
                  <span className="roadmap-layer-blurb">{row.plain}</span>
                  <span
                    className="roadmap-layer-status"
                    data-testid="roadmap-aim-status"
                  >
                    {row.status}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <section id="suggest-a-layer" data-testid="roadmap-suggest-layer">
        <h2>Suggest a layer</h2>
        <p>{SUGGEST_LAYER_COPY}</p>
        <p>
          <a href={SUGGEST_LAYER_HREF}>Suggest a layer</a>
        </p>
      </section>

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

      <section id="further-ahead" data-testid="roadmap-further-ahead">
        <h2>Further ahead</h2>
        <ul className="roadmap-layer-list">
          <li data-testid="roadmap-layer-row">
            <span className="roadmap-layer-name">
              Land values for each piece of land, per square metre
            </span>
            <span className="roadmap-layer-status">
              <span className="roadmap-waiting-status-full">Not started</span>
            </span>
          </li>
          <li data-testid="roadmap-layer-row">
            <span className="roadmap-layer-name">
              Bulk data downloads and full API (may be paid)
            </span>
            <span className="roadmap-layer-status">
              <span className="roadmap-waiting-status-full">Not started</span>
            </span>
          </li>
        </ul>
      </section>

      <div className="content-page-footer-wrap">
        <ContentPageFooter />
      </div>
    </main>
  );
}

import type { Metadata } from "next";
import ContentPageFooter from "@/components/ContentPageFooter";
import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
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
    status: "Not started",
  })),
  {
    name: "Landscape character areas",
    status: "Waiting for permission — licence check",
  },
  {
    name: "Fish and shellfish farms",
    status: "Being checked — source unreliable",
  },
  {
    name: "Public land owned by the Crown",
    status: "Not started",
  },
];

type AimStatus = "Live" | "In progress" | "Not started" | "Later";

type AimRow = {
  name: string;
  plain: string;
  status: AimStatus;
};

type AimGroup = {
  id: string;
  heading: string;
  rows: readonly AimRow[];
};

/**
 * RENTS-1 Part 2, one row each.
 * Live only when the public site shows that rent. Amounts are withheld, and the
 * working map layers (wind, seabed leases, oil fields, council fill) are context
 * with no rent figure — so none are Live.
 * In progress: the place card already covers homes, or a live Layers switch
 * paints that subject today.
 * Later: parked after the current homes work, or a breakdown the card does not show.
 */
const AIM_TO_COVER: readonly AimGroup[] = [
  {
    id: "land",
    heading: "Land (Annual Ground Rent)",
    rows: [
      {
        name: "Site rent: homes",
        plain:
          "Yearly rental value of the land under homes, without the buildings.",
        status: "In progress",
      },
      {
        name: "Site rent: business",
        plain:
          "Yearly rental value of the land under shops, offices and works.",
        status: "Later",
      },
      {
        name: "Site rent: farmland",
        plain: "Yearly rental value of farmland, without farm buildings.",
        status: "Not started",
      },
      {
        name: "Planning uplift",
        plain:
          "Extra value land gains from planning permission. It sits inside the land rent and is not added again.",
        status: "Not started",
      },
      {
        name: "Infrastructure commons uplift",
        plain:
          "Land value created by public spending on roads, rail and services. It sits inside the land rent and is not added again.",
        status: "Later",
      },
      {
        name: "Licences and franchises",
        plain:
          "Value of exclusive rights granted by government, such as ferry routes, broadcasting and taxi plates.",
        status: "Later",
      },
      {
        name: "Monopoly and other artificial privileges",
        plain:
          "Excess return from barriers to entry or a legal privilege.",
        status: "Later",
      },
    ],
  },
  {
    id: "resources",
    heading: "Natural resource rents",
    rows: [
      {
        name: "Minerals and aggregates",
        plain:
          "Royalty for each tonne of stone, sand, gravel or coal taken from the ground.",
        status: "Not started",
      },
      {
        name: "Oil and gas",
        plain:
          "Rent from oil and gas fields beyond what extraction costs plus a normal return.",
        status: "In progress",
      },
      {
        name: "Water abstraction",
        plain:
          "Value of taking water from rivers, lochs and the ground under licence.",
        status: "Not started",
      },
      {
        name: "Fishing quota",
        plain: "Value of the right to catch a share of fish stocks.",
        status: "Not started",
      },
      {
        name: "Fish-farm seabed leases",
        plain:
          "Rent for fish farm sites on the seabed, beyond the lease paid to Crown Estate Scotland.",
        status: "Not started",
      },
      {
        name: "Onshore wind and hydro sites",
        plain:
          "Extra rent a wind or hydro site earns over ordinary land rent on the same ground.",
        status: "In progress",
      },
      {
        name: "Offshore wind and seabed",
        plain:
          "Rent for seabed and foreshore used for wind farms, cables and moorings.",
        status: "In progress",
      },
      {
        name: "Timber",
        plain:
          "Value of the standing trees' site, beyond planting and management costs.",
        status: "Not started",
      },
      {
        name: "Radio spectrum",
        plain: "Value of the right to use radio frequencies.",
        status: "Later",
      },
      {
        name: "Orbits and airspace",
        plain: "Value of orbital slots and airspace rights.",
        status: "Later",
      },
    ],
  },
  {
    id: "nature",
    heading: "Services of nature",
    rows: [
      {
        name: "Carbon in peat and soils",
        plain:
          "Value of carbon kept in the ground by peat and soils, where there is no market price.",
        status: "Not started",
      },
      {
        name: "Flood regulation, pollination, clean water, recreation",
        plain: "Other free services of nature.",
        status: "Not started",
      },
    ],
  },
];

const OUR_VISION_HEADING = "Our vision";

const OUR_VISION_TEXT =
  "Our long-term aim is to give every piece of land in Scotland its own Annual Ground Rent value, per square metre. Today we show estimates for small areas, called Data Zones. Next we plan to work at the level of individual land parcels, and then on a fine 3-metre grid. We are building this step by step from accurate, publicly available data. Getting it right will take time, and we will keep refining it until it is accurate enough to be a trusted source of land value information for Scotland.";

export default function RoadmapPage() {
  return (
    <main className="methodology-page" data-testid="roadmap-page">
      <SiteNav />
      <h1>Roadmap</h1>
      <ResearchBanner />

      <section id="our-vision" data-testid="roadmap-vision">
        <h2>{OUR_VISION_HEADING}</h2>
        <p>{OUR_VISION_TEXT}</p>
      </section>

      <section id="what-we-aim-to-cover" data-testid="roadmap-aim">
        <h2>What we aim to cover</h2>
        {AIM_TO_COVER.map((group) => (
          <div key={group.id} data-testid={`roadmap-aim-group-${group.id}`}>
            <h3>{group.heading}</h3>
            <ul className="roadmap-layer-list">
              {group.rows.map((row) => (
                <li key={row.name} data-testid="roadmap-aim-row">
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

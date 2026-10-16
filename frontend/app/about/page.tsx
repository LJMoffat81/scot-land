import type { Metadata } from "next";
import MissionContent from "@/components/MissionContent";
import { OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "About | Scot-LAND",
  description:
    "Scot-LAND is a free, open map of Scotland's land, built around Annual Ground Rent: the yearly value of land we all create. Research estimate, not a bill or an official valuation.",
  openGraph: {
    title: "About | Scot-LAND",
    description:
      "Scot-LAND is a free, open map of Scotland's land, built around Annual Ground Rent: the yearly value of land we all create. Research estimate, not a bill or an official valuation.",
    images: [...OG_IMAGES],
  },
};

export default function AboutPage() {
  return <MissionContent />;
}

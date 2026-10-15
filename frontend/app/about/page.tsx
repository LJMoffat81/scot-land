import type { Metadata } from "next";
import MissionContent from "@/components/MissionContent";
import { OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "About | Scot-LAND",
  description:
    "Scot-LAND is a free, open map of Scotland's land, built around Annual Ground Rent (sometimes called land value tax). Research estimate — figures are not published yet.",
  openGraph: {
    title: "About | Scot-LAND",
    description:
      "Scot-LAND is a free, open map of Scotland's land, built around Annual Ground Rent (sometimes called land value tax). Research estimate — figures are not published yet.",
    images: [...OG_IMAGES],
  },
};

export default function AboutPage() {
  return <MissionContent />;
}

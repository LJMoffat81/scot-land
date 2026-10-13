import type { Metadata } from "next";
import MissionContent from "@/components/MissionContent";

export const metadata: Metadata = {
  title: "Mission | Scot-LAND",
  description:
    "Scot-LAND’s purpose is Annual Ground Rent for every place in Scotland. Research estimate, not an official valuation or bill. Figures pending sign-off.",
  openGraph: {
    title: "Mission | Scot-LAND",
    description:
      "Scot-LAND’s purpose is Annual Ground Rent for every place in Scotland. Research estimate, not an official valuation or bill. Figures pending sign-off.",
  },
};

export default function MissionPage() {
  return <MissionContent />;
}

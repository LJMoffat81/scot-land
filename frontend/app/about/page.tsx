import type { Metadata } from "next";
import MissionContent from "@/components/MissionContent";

export const metadata: Metadata = {
  title: "About | Scot-LAND",
  description:
    "What Scot-LAND is, why it is being built, and how to get in touch. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "About | Scot-LAND",
    description:
      "What Scot-LAND is, why it is being built, and how to get in touch. Research estimate — land rent figures are not published yet.",
  },
};

export default function AboutPage() {
  return <MissionContent />;
}

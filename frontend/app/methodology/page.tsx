import type { Metadata } from "next";
import MethodologyContent from "@/components/MethodologyContent";

export const metadata: Metadata = {
  title: "How it works | Scot-LAND",
  description:
    "How Scot-LAND estimates Annual Ground Rent for Data Zones: market, proxy and shadow tags, sources and licences. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "How it works | Scot-LAND",
    description:
      "How Scot-LAND estimates Annual Ground Rent for Data Zones: market, proxy and shadow tags, sources and licences. Research estimate — land rent figures are not published yet.",
  },
};

export default function MethodologyPage() {
  return <MethodologyContent />;
}

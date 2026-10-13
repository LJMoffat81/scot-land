import type { Metadata } from "next";
import MethodologyContent from "@/components/MethodologyContent";

export const metadata: Metadata = {
  title: "Methodology | Scot-LAND",
  description:
    "How Scot-LAND estimates Annual Ground Rent: Data Zone roll-up, market/proxy/shadow tags, sources and licences. Research estimate; figures pending sign-off.",
  openGraph: {
    title: "Methodology | Scot-LAND",
    description:
      "How Scot-LAND estimates Annual Ground Rent: Data Zone roll-up, market/proxy/shadow tags, sources and licences. Research estimate; figures pending sign-off.",
  },
};

export default function MethodologyPage() {
  return <MethodologyContent />;
}

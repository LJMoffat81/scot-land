import type { Metadata } from "next";
import MethodologyContent from "@/components/MethodologyContent";

export const metadata: Metadata = {
  title: "About | Scot-LAND",
  description:
    "How Scot-LAND’s experimental commons engine works: Surface, Resource and Eco — quality-tagged, not an official valuation.",
  openGraph: {
    title: "About | Scot-LAND",
    description:
      "How Scot-LAND’s experimental commons engine works: Surface, Resource and Eco — quality-tagged, not an official valuation.",
  },
};

export default function MethodologyPage() {
  return <MethodologyContent />;
}

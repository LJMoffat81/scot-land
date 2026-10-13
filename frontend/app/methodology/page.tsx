import type { Metadata } from "next";
import MethodologyContent from "@/components/MethodologyContent";

export const metadata: Metadata = {
  title: "About | Scot-LAND",
  description:
    "Scot-LAND’s purpose is Annual Ground Rent — the rent of land at every place in Scotland. £ figures not published yet; experimental research only.",
  openGraph: {
    title: "About | Scot-LAND",
    description:
      "Scot-LAND’s purpose is Annual Ground Rent — the rent of land at every place in Scotland. £ figures not published yet; experimental research only.",
  },
};

export default function MethodologyPage() {
  return <MethodologyContent />;
}

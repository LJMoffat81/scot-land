import type { Metadata } from "next";
import MethodologyContent from "@/components/MethodologyContent";

export const metadata: Metadata = {
  title: "How it works | Scot-LAND",
  description:
    "How Scot-LAND values land for a Data Zone: towns, countryside, natural resources and limits on use. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "How it works | Scot-LAND",
    description:
      "How Scot-LAND values land for a Data Zone: towns, countryside, natural resources and limits on use. Research estimate — land rent figures are not published yet.",
  },
};

export default function MethodologyPage() {
  return <MethodologyContent />;
}

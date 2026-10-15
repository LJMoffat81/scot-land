import type { Metadata } from "next";
import MethodologyContent from "@/components/MethodologyContent";
import { OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "How it works | Scot-LAND",
  description:
    "How Scot-LAND values land for a Data Zone: towns, countryside, natural resources and limits on use. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "How it works | Scot-LAND",
    description:
      "How Scot-LAND values land for a Data Zone: towns, countryside, natural resources and limits on use. Research estimate — land rent figures are not published yet.",
    images: [...OG_IMAGES],
  },
};

export default function MethodologyPage() {
  return <MethodologyContent />;
}

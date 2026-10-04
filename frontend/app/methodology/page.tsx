import type { Metadata } from "next";
import MethodologyContent from "@/components/MethodologyContent";

export const metadata: Metadata = {
  title: "About | Scot-LAND",
  description:
    "How Scot-LAND estimates Annual Ground Rent for a place, on land value only. Research estimate, not a bill.",
  openGraph: {
    title: "About | Scot-LAND",
    description:
      "How Scot-LAND estimates Annual Ground Rent for a place, on land value only. Research estimate, not a bill.",
  },
};

export default function MethodologyPage() {
  return <MethodologyContent />;
}

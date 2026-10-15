import type { Metadata } from "next";

import { OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "Technical checks | Scot-LAND",
  description:
    "Automatic tests that check Scot-LAND sums follow the rules. For developers and reviewers.",
  openGraph: {
    title: "Technical checks | Scot-LAND",
    description:
      "Automatic tests that check Scot-LAND sums follow the rules. For developers and reviewers.",
    images: [...OG_IMAGES],
  },
};

export default function DevelopersChecksLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

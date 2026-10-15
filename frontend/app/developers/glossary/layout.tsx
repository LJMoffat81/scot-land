import type { Metadata } from "next";

import { OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "Glossary | Scot-LAND",
  description:
    "Developer glossary for Scot-LAND valuation terms. For developers and reviewers — not linked from visitor pages.",
  openGraph: {
    title: "Glossary | Scot-LAND",
    description:
      "Developer glossary for Scot-LAND valuation terms. For developers and reviewers.",
    images: [...OG_IMAGES],
  },
};

export default function DevelopersGlossaryLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

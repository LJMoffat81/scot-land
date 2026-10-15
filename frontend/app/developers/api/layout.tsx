import type { Metadata } from "next";

import { OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "API reference | Scot-LAND",
  description:
    "Interactive OpenAPI reference for the Scot-LAND place and layer API. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "API reference | Scot-LAND",
    description:
      "Interactive OpenAPI reference for the Scot-LAND place and layer API. Research estimate — land rent figures are not published yet.",
    images: [...OG_IMAGES],
  },
};

export default function ApiDocsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

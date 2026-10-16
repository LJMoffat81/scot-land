import type { Metadata } from "next";

import { OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "Developer API and bulk data | Scot-LAND",
  description:
    "We plan to offer a developer API and bulk downloads. The map stays free to use. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "Developer API and bulk data | Scot-LAND",
    description:
      "We plan to offer a developer API and bulk downloads. The map stays free to use. Research estimate — land rent figures are not published yet.",
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

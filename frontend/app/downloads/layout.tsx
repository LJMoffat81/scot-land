import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Downloads | Scot-LAND",
  description:
    "Open tables and source links behind Scot-LAND’s experimental commons map. Not an official valuation.",
  openGraph: {
    title: "Downloads | Scot-LAND",
    description:
      "Open tables and source links behind Scot-LAND’s experimental commons map. Not an official valuation.",
  },
};

export default function DownloadsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

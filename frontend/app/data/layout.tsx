import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Data & sources | Scot-LAND",
  description:
    "Open data sources, licences, gaps and excluded lists behind the Scot-LAND map. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "Data & sources | Scot-LAND",
    description:
      "Open data sources, licences, gaps and excluded lists behind the Scot-LAND map. Research estimate — land rent figures are not published yet.",
  },
};

export default function DataLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

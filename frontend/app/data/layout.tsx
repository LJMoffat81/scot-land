import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Data & sources | Scot-LAND",
  description:
    "Open data sources, licences, gaps and what Scot-LAND leaves out. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "Data & sources | Scot-LAND",
    description:
      "Open data sources, licences, gaps and what Scot-LAND leaves out. Research estimate — land rent figures are not published yet.",
  },
};

export default function DataLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Downloads | Scot-LAND",
  description:
    "Open tables and source links that feed Scot-LAND’s Annual Ground Rent map. £ figures not published yet.",
  openGraph: {
    title: "Downloads | Scot-LAND",
    description:
      "Open tables and source links that feed Scot-LAND’s Annual Ground Rent map. £ figures not published yet.",
  },
};

export default function DownloadsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Downloads | Scot-LAND",
  description:
    "Open tables of the Annual Ground Rent figures behind the map. Research estimate, not a bill.",
  openGraph: {
    title: "Downloads | Scot-LAND",
    description:
      "Open tables of the Annual Ground Rent figures behind the map. Research estimate, not a bill.",
  },
};

export default function DownloadsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Downloads & API | Scot-LAND",
  description:
    "Download open Scot-LAND tables and use the place and layer API. Free under the licence shown. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "Downloads & API | Scot-LAND",
    description:
      "Download open Scot-LAND tables and use the place and layer API. Research estimate — land rent figures are not published yet.",
  },
};

export default function DevelopersLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

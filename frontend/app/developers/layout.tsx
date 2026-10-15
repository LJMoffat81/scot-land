import type { Metadata } from "next";

import ContentPageFooter from "@/components/ContentPageFooter";
import { OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "Downloads & API | Scot-LAND",
  description:
    "Download open Scot-LAND tables and use the place and layer API. Free under the licence shown. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "Downloads & API | Scot-LAND",
    description:
      "Download open Scot-LAND tables and use the place and layer API. Research estimate — land rent figures are not published yet.",
    images: [...OG_IMAGES],
  },
};

export default function DevelopersLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <>
      {children}
      <div className="content-page-footer-wrap">
        <ContentPageFooter />
      </div>
    </>
  );
}

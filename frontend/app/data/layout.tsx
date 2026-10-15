import type { Metadata } from "next";

import ContentPageFooter from "@/components/ContentPageFooter";
import DataLicencesAnchor from "@/components/DataLicencesAnchor";
import { OG_IMAGES } from "@/lib/socialMeta";

export const metadata: Metadata = {
  title: "Data & sources | Scot-LAND",
  description:
    "Open data sources, licences, gaps and what Scot-LAND leaves out. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "Data & sources | Scot-LAND",
    description:
      "Open data sources, licences, gaps and what Scot-LAND leaves out. Research estimate — land rent figures are not published yet.",
    images: [...OG_IMAGES],
  },
};

export default function DataLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <>
      <DataLicencesAnchor />
      {children}
      <div className="content-page-footer-wrap">
        <ContentPageFooter />
      </div>
    </>
  );
}

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "API reference | Scot-LAND",
  description:
    "Interactive OpenAPI reference for the Scot-LAND place and layer API. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "API reference | Scot-LAND",
    description:
      "Interactive OpenAPI reference for the Scot-LAND place and layer API. Research estimate — land rent figures are not published yet.",
  },
};

export default function ApiDocsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

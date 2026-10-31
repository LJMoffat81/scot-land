import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Get the data | Scot-LAND",
  description:
    "Redirects to Get the data. Research estimate — land rent figures are not published yet.",
};

export default function DownloadsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

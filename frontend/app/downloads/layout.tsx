import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Downloads & API | Scot-LAND",
  description:
    "Redirects to Downloads & API. Research estimate — land rent figures are not published yet.",
};

export default function DownloadsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

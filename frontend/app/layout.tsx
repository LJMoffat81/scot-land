import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import "./platform.css";

const mona = localFont({
  src: "../node_modules/@fontsource-variable/mona-sans/files/mona-sans-latin-wght-normal.woff2",
  weight: "200 900",
  display: "swap",
  fallback: ["Segoe UI", "Helvetica", "Arial", "sans-serif"],
});

export const metadata: Metadata = {
  title: "Map | Scot-LAND",
  description:
    "Search a Scottish postcode, place or map reference on an open land map. Research estimate — land rent figures are not published yet.",
  openGraph: {
    title: "Map | Scot-LAND",
    description:
      "Find a place on Scotland’s open land map. Research estimate — land rent figures are not published yet.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={mona.className}>{children}</body>
    </html>
  );
}

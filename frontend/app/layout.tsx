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
  title: "Scot-LAND — open map of Scotland’s land",
  description:
    "Search a Scottish postcode, place or coordinates on an open land map. Research estimates, not a bill.",
  openGraph: {
    title: "Scot-LAND — open map of Scotland’s land",
    description:
      "Find a place on Scotland’s open land map. Ownership and research land-rent figures follow; not a tax bill.",
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

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
  title: "SCOT-LAND MEGA BUILD 2026",
  description:
    "A research estimate of what Scotland's land alone is worth to use each year, by postcode. Not a bill.",
  openGraph: {
    title: "Scot-LAND: what is Scotland's land worth each year?",
    description:
      "Search any Scottish postcode for a research estimate of its Annual Ground Rent, on land value only.",
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

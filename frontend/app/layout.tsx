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
  title: "Scot-LAND",
  description:
    "Annual Ground Rent at every place in Scotland. https://www.scot-land.scot",
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

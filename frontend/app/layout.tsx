import type { Metadata } from "next";
import { DM_Sans } from "next/font/google";
import "./globals.css";
import "./platform.css";

const dmSans = DM_Sans({
  subsets: ["latin"],
  display: "swap",
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
      <body className={dmSans.className}>{children}</body>
    </html>
  );
}

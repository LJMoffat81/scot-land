import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Place | Scot-LAND",
  description:
    "Annual Ground Rent breakdown for a Data Zone. Research estimate — figures are not published yet.",
};

export default function PlaceLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

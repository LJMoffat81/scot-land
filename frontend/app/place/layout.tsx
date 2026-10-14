import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Place | Scot-LAND",
  description:
    "Natural capital per-hectare stack for a Data Zone. Research estimate — land rent figures are not published yet.",
};

export default function PlaceLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Place — per-hectare ledger stack",
  description:
    "Natural capital per-hectare stack for a Data Zone. Figures are being checked and aren't published yet — research estimate, not a rates bill.",
};

export default function PlaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}

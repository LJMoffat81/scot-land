import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Place — per-hectare ledger stack",
  description:
    "Zone-level Natural capital per-hectare stack: headline market+proxy, nested planning uplift, separate shadow stack. Placeholders until ECONOMIC_RULES — not a rates bill.",
};

export default function PlaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}

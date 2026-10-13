import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Data — Checks & excluded | Scot-LAND",
  description:
    "Natural capital ledger checks (C-hectare…C-cap), excluded list with reasons, and benchmarks labelled not inputs.",
  openGraph: {
    title: "Data — Checks & excluded | Scot-LAND",
    description:
      "Natural capital ledger checks, exclusions, and benchmarks (not inputs).",
  },
};

export default function DataLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

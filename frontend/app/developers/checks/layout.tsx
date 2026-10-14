import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Technical checks | Scot-LAND",
  description:
    "Automatic tests that check Scot-LAND sums follow the rules. For developers and reviewers.",
  openGraph: {
    title: "Technical checks | Scot-LAND",
    description:
      "Automatic tests that check Scot-LAND sums follow the rules. For developers and reviewers.",
  },
};

export default function DevelopersChecksLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return children;
}

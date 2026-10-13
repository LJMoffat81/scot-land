import type { ReactNode } from "react";
import { notFound } from "next/navigation";

import { internalUiEnabled } from "@/lib/internalUi";

export default function PlaceCardLayout({
  children,
}: {
  children: ReactNode;
}) {
  if (!internalUiEnabled()) notFound();
  return children;
}

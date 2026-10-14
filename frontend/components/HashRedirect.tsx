"use client";

import { useEffect } from "react";

export type HashRedirectProps = {
  /** Hash without #, e.g. "why". */
  fromHash: string;
  /** Absolute path (+ optional hash), e.g. "/about#why". */
  to: string;
};

/**
 * Client-side permanent-style hash redirects (spec A).
 * Used for /methodology#why → /about#why and /data#checks → /developers/checks.
 */
export default function HashRedirect({ fromHash, to }: HashRedirectProps) {
  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, "");
    if (hash === fromHash) {
      window.location.replace(to);
    }
  }, [fromHash, to]);

  return null;
}

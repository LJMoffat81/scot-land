"use client";

import { useEffect } from "react";

/**
 * Ensures /data#licences resolves without editing the data page body
 * (owned by a parallel draft). Pins an anchor at the sources table.
 */
export default function DataLicencesAnchor() {
  useEffect(() => {
    if (document.getElementById("licences")) return;
    const sources = document.getElementById("sources");
    const host = document.createElement("span");
    host.id = "licences";
    host.setAttribute("data-testid", "data-licences-anchor");
    if (sources?.parentElement) {
      sources.parentElement.insertBefore(host, sources);
    } else {
      document.body.prepend(host);
    }
  }, []);

  return null;
}

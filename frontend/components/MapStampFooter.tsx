"use client";

<<<<<<< HEAD
import { useEffect, useState } from "react";
import { apiJson, engineVersionLine, type EngineStamp } from "../lib/api";

const DEVELOPMENT_NOTICE =
  "Research estimate. Annual Ground Rent figures are not published yet. They are not a bill or an official valuation.";

/** Footer stamp for the public map shell (no AGR £ breakdown). */
=======
/**
 * One-line map footer (site-watch PR A items 2 + 5).
 * Research notice lives in the banner only — not repeated here.
 */
>>>>>>> 344ab6c (fix(frontend): site-watch PR A — page chrome (items 1–7, SW-010/011))
export function MapStampFooter() {
  return (
    <footer className="map-footer" data-testid="map-stamp-footer">
      <p data-testid="map-footer-line">
        Research estimate · Open data ·{" "}
        <a href="/data#licences">Sources and licences</a>
      </p>
    </footer>
  );
}

export default MapStampFooter;

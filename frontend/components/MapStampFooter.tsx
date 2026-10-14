"use client";

/**
 * One-line map footer (site-watch PR A items 2 + 5).
 * Research notice lives in the banner only — not repeated here.
 */
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

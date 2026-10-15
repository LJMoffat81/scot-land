"use client";

import {
  anyNonCommercial,
  type MapCreditEntry,
} from "@/lib/mapLicenceCredits";

export type MapLicenceCreditsProps = {
  credits: MapCreditEntry[];
  className?: string;
};

/**
 * Map licence credits control — one line per active catalog layer.
 * Driven by catalogue `licence` / `licence_url` / `attribution` fields.
 * Shows a non-commercial badge when any credited layer is NC-only.
 */
export default function MapLicenceCredits({
  credits,
  className,
}: MapLicenceCreditsProps) {
  if (credits.length === 0) return null;
  const showNc = anyNonCommercial(credits);

  // Group (not complementary): the legend panel is already an aside landmark.
  // Keeps "Map data licences" as a unique accessible name without a second landmark.
  return (
    <div
      className={["map-licence-credits", className].filter(Boolean).join(" ")}
      role="group"
      aria-label="Map data licences"
      data-testid="map-licence-credits"
    >
      <p className="map-licence-credits-title">Data licences</p>
      {showNc ? (
        <p
          className="map-licence-nc-badge"
          data-testid="map-non-commercial-badge"
          title="One or more visible layers are licensed for non-commercial use only"
        >
          Non-commercial use only
        </p>
      ) : null}
      <ul className="map-licence-credits-list">
        {credits.map((credit) => (
          <li
            key={credit.layerId}
            data-testid={`map-credit-${credit.layerId}`}
            data-non-commercial={credit.nonCommercial ? "1" : "0"}
          >
            <span className="map-licence-credits-label">{credit.label}</span>
            <span className="map-licence-credits-licence">
              Licence:{" "}
              {credit.licenceUrl ? (
                <a
                  href={credit.licenceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid={`map-credit-licence-link-${credit.layerId}`}
                >
                  {credit.licence}
                </a>
              ) : (
                credit.licence
              )}
            </span>
            <span className="map-licence-credits-attribution">
              {credit.attribution}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

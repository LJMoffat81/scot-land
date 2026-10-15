/**
 * Data Zone 2022 publisher attribution — year from the manifest-synced export
 * (dz2022ExtractionYear.mjs ← dz2022Attribution.json ← sources.yaml).
 */

import { DZ2022_EXTRACTION_YEAR } from "./dz2022ExtractionYear.mjs";

export { DZ2022_EXTRACTION_YEAR };

/**
 * Exact publisher credit (spatialdata.gov.scot record; MAP-CARDS addendum).
 * Year is never hard-coded at the call site — always from the manifest export.
 */
export function dz2022CopyrightLine(
  year: number = DZ2022_EXTRACTION_YEAR,
): string {
  return (
    "Copyright Scottish Government, contains Ordnance Survey data © Crown " +
    `copyright and database right ${year}.`
  );
}

/** MAP-CARDS GIS 14 / addendum — alias used by the map attribution line. */
export function dzAttributionText(
  year: number = DZ2022_EXTRACTION_YEAR,
): string {
  return dz2022CopyrightLine(year);
}

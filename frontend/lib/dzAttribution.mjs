/**
 * Node-script entry for DZ2022 attribution (same strings as dzAttribution.ts).
 */

import { DZ2022_EXTRACTION_YEAR } from "./dz2022ExtractionYear.mjs";

export { DZ2022_EXTRACTION_YEAR };

export function dz2022CopyrightLine(year = DZ2022_EXTRACTION_YEAR) {
  return (
    "Copyright Scottish Government, contains Ordnance Survey data © Crown " +
    `copyright and database right ${year}.`
  );
}

export function dzAttributionText(year = DZ2022_EXTRACTION_YEAR) {
  return dz2022CopyrightLine(year);
}

/**
 * Data Zone 2022 publisher attribution — year from committed manifest JSON
 * (sourced from data/config/sources.yaml data_zone_boundaries.vintages.2022).
 * .mjs so Node unit scripts can import without JSON import attributes.
 */

import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const dz2022Attribution = require("./dz2022Attribution.json");

export const DZ2022_EXTRACTION_YEAR = dz2022Attribution.extraction_year;

/**
 * Exact publisher credit (spatialdata.gov.scot record; MAP-CARDS addendum).
 * Year is never hard-coded at the call site — always from the manifest.
 */
export function dz2022CopyrightLine(year = DZ2022_EXTRACTION_YEAR) {
  return (
    "Copyright Scottish Government, contains Ordnance Survey data © Crown " +
    `copyright and database right ${year}.`
  );
}

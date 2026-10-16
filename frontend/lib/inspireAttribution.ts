/**
 * Confirmed RoS INSPIRE Index Polygons credit (Oct 2026).
 * Map credit + layer guide must use this exact wording; year = harvest year.
 * OGL v3 only — never the 2017 OS INSPIRE end-user licence.
 */

export const INSPIRE_HARVEST_YEAR = 2026;

export const INSPIRE_OGL_V3_URL =
  "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/";

export const INSPIRE_OGL_V3_PHRASE =
  "Licensed under the Open Government Licence v3.0";

/** Exact map / layer-guide credit line. */
export function inspireRosOsAttribution(
  year: number = INSPIRE_HARVEST_YEAR,
): string {
  return (
    "© Crown copyright. Reproduced with the permission of Registers of Scotland. " +
    `Contains OS data © Crown copyright and database right ${year}.`
  );
}

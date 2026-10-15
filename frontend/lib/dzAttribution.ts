/**
 * Typed re-export of DZ2022 attribution (runtime in dzAttribution.mjs).
 */

import {
  DZ2022_EXTRACTION_YEAR as _YEAR,
  dz2022CopyrightLine as _line,
  dzAttributionText as _attr,
} from "./dzAttribution.mjs";

export const DZ2022_EXTRACTION_YEAR = _YEAR as number;

export function dz2022CopyrightLine(
  year: number = DZ2022_EXTRACTION_YEAR,
): string {
  return _line(year);
}

/** MAP-CARDS GIS 14 — year from JSON manifest, never hard-coded at call sites. */
export function dzAttributionText(
  year: number = DZ2022_EXTRACTION_YEAR,
): string {
  return _attr(year);
}

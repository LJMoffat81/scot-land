/**
 * Data-state quality tags (live | derived | modelled | placeholder).
 * Distinct from catalog status (live|linked|gap) and value tier (market|proxy|shadow).
 */

export const QUALITY_TAGS = ["live", "derived", "modelled", "placeholder"] as const;

export type QualityTagId = (typeof QUALITY_TAGS)[number];

export const QUALITY_TAG_LABELS: Record<QualityTagId, string> = {
  live: "live",
  derived: "derived",
  modelled: "modelled",
  placeholder: "placeholder",
};

/** Short public gloss for methodology and docs surfaces. */
export const QUALITY_TAG_GLOSS: Record<QualityTagId, string> = {
  live: "observed from a public source as-is",
  derived: "computed from open inputs by a stated method",
  modelled:
    "estimated by the residual / mass model; money figures stay unpublished until calibration is checked",
  placeholder: "not ready; never served on the public API or map",
};

export function isQualityTag(value: string | undefined | null): value is QualityTagId {
  if (!value) return false;
  return (QUALITY_TAGS as readonly string[]).includes(value);
}

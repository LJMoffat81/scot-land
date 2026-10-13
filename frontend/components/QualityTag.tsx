import {
  QUALITY_TAG_LABELS,
  type QualityTagId,
  isQualityTag,
} from "@/lib/qualityTag";

export type QualityTagProps = {
  quality: QualityTagId | string;
  className?: string;
};

/**
 * Coloured chip for data-state quality tags.
 * Uses `.quality-tag.tone-*` so styles never collide with LayersPanel catalog status.
 */
export default function QualityTag({ quality, className }: QualityTagProps) {
  const tone: QualityTagId = isQualityTag(quality) ? quality : "placeholder";
  const label = isQualityTag(quality)
    ? QUALITY_TAG_LABELS[quality]
    : String(quality || "unknown");

  return (
    <span
      className={["quality-tag", `tone-${tone}`, className]
        .filter(Boolean)
        .join(" ")}
      data-testid="quality-tag"
      data-quality={tone}
    >
      {label}
    </span>
  );
}

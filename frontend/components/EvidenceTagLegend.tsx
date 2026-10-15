import ConfidenceTag, {
  EVIDENCE_TAG_GLOSS,
  type ConfidenceTagKind,
} from "@/components/ConfidenceTag";

export { EVIDENCE_TAG_GLOSS };

const ORDER: ConfidenceTagKind[] = ["market", "proxy", "shadow"];

export type EvidenceTagLegendProps = {
  className?: string;
  /** Compact one-line chips vs listed glosses. */
  compact?: boolean;
};

/**
 * Market / Modelled / Estimate chip key — mount once in the map legend (SW-044).
 */
export default function EvidenceTagLegend({
  className,
  compact = false,
}: EvidenceTagLegendProps) {
  return (
    <ul
      className={["evidence-tag-legend", className].filter(Boolean).join(" ")}
      data-testid="evidence-tag-legend"
      aria-label="Evidence tags"
    >
      {ORDER.map((kind) => (
        <li
          key={kind}
          className={
            compact
              ? "evidence-tag-legend-item compact"
              : "evidence-tag-legend-item"
          }
          data-testid={`evidence-tag-legend-${kind}`}
        >
          <ConfidenceTag kind={kind} />
          <span className="evidence-tag-legend-gloss">
            {compact ? `= ${EVIDENCE_TAG_GLOSS[kind]}` : EVIDENCE_TAG_GLOSS[kind]}
          </span>
        </li>
      ))}
    </ul>
  );
}

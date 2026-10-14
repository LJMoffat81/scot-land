import ConfidenceTag, {
  type ConfidenceTagKind,
} from "@/components/ConfidenceTag";

/** Redesign three-chip legend copy (drawer + place card + methodology). */
export const EVIDENCE_TAG_GLOSS: Record<ConfidenceTagKind, string> = {
  market: "based on real sales or prices",
  proxy: "modelled from similar evidence",
  shadow: "a value with no market price",
};

const ORDER: ConfidenceTagKind[] = ["market", "proxy", "shadow"];

export type EvidenceTagLegendProps = {
  className?: string;
  /** Compact one-line chips vs listed glosses. */
  compact?: boolean;
};

/**
 * Market / Proxy / Shadow legend — mount once in the layers drawer and place card.
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

export type ConfidenceTagKind = "market" | "proxy" | "shadow";

/** FP1 / AGENTS: chips are Market / Modelled / Estimate (never "market price"). */
const LABEL: Record<ConfidenceTagKind, string> = {
  market: "Market",
  proxy: "Modelled",
  shadow: "Estimate",
};

/** Chip meanings — tooltip + aria-description; legend gloss uses the same copy. */
export const EVIDENCE_TAG_GLOSS: Record<ConfidenceTagKind, string> = {
  market: "taken from real prices people paid",
  proxy: "worked out from related prices",
  shadow: "used when there is no market price",
};

export default function ConfidenceTag({
  kind,
}: {
  kind: ConfidenceTagKind;
}) {
  const description = EVIDENCE_TAG_GLOSS[kind];
  return (
    <span
      className={`confidence-tag tone-${kind}`}
      data-testid="confidence-tag"
      data-confidence={kind}
      title={description}
      aria-description={description}
    >
      {LABEL[kind]}
    </span>
  );
}

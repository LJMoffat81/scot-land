export type ConfidenceTagKind = "market" | "proxy" | "shadow";

/** FP1 / AGENTS: chips are Market / Modelled / Estimate (never "market price"). */
const LABEL: Record<ConfidenceTagKind, string> = {
  market: "Market",
  proxy: "Modelled",
  shadow: "Estimate",
};

export default function ConfidenceTag({
  kind,
}: {
  kind: ConfidenceTagKind;
}) {
  return (
    <span
      className={`confidence-tag tone-${kind}`}
      data-testid="confidence-tag"
      data-confidence={kind}
    >
      {LABEL[kind]}
    </span>
  );
}

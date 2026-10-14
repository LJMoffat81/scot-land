export type ConfidenceTagKind = "market" | "proxy" | "shadow";

const LABEL: Record<ConfidenceTagKind, string> = {
  market: "Market",
  proxy: "Modelled",
  shadow: "Estimate (no market price)",
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

export type ConfidenceTagKind = "market" | "proxy" | "shadow";

const LABEL: Record<ConfidenceTagKind, string> = {
  market: "Market",
  proxy: "Proxy",
  shadow: "Shadow",
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

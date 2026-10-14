/**
 * Shared glossary for How it works and Data & sources (site rewrite section B).
 */

export const GLOSSARY_TERMS = [
  {
    id: "agr",
    term: "Annual Ground Rent",
    definition:
      "the yearly rental value of a site, the land without its buildings. It is public value, created by the community and by nature, not by the owner.",
  },
  {
    id: "data-zone",
    term: "Data Zone",
    definition:
      "a small area used by the Scottish Government for statistics, usually home to 500–1,000 people. Scotland has about 7,400 of them (2022 set). We show figures for Data Zones, never for single plots.",
  },
  {
    id: "tags",
    term: "Market / Modelled / Estimate (no market price)",
    definition:
      "how a figure was found. Market = taken from real prices people paid. Modelled = worked out from related prices. Estimate (no market price) = used when there is no market price, like peat holding carbon. We never add different kinds together.",
  },
  {
    id: "constraint",
    term: "Constraint",
    definition:
      "a rule that limits how land can be used, like a nature protection area or flood risk. Constraint: changes best use, adds no value.",
  },
  {
    id: "ogl",
    term: "OGL",
    definition:
      "the Open Government Licence. It lets anyone use, share and build on public data if they say where it came from.",
  },
] as const;

export type GlossaryBoxProps = {
  /** Section heading — How it works uses “Three kinds of figure”. */
  title?: string;
};

export default function GlossaryBox({ title = "Glossary" }: GlossaryBoxProps) {
  return (
    <section
      id="glossary"
      className="glossary-box"
      data-testid="glossary-box"
      aria-labelledby="glossary-heading"
    >
      <h2 id="glossary-heading">{title}</h2>
      <dl className="glossary-list">
        {GLOSSARY_TERMS.map((item) => (
          <div key={item.id} className="glossary-item" id={`glossary-${item.id}`}>
            <dt>{item.term}</dt>
            <dd>{item.definition}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/**
 * Developer glossary terms — keep in sync with docs/GLOSSARY.md.
 * The glossary block may define "shadow"; the HTML guard strips only that block.
 */

export type DevelopersGlossaryEntry = {
  term: string;
  /** Optional chip label shown after the term, e.g. "(chip: Market)". */
  chip?: string;
  definition: string;
};

export const DEVELOPERS_GLOSSARY_TITLE = "Scot-LAND glossary";

export const DEVELOPERS_GLOSSARY_TERMS: readonly DevelopersGlossaryEntry[] = [
  {
    term: "Land value",
    definition:
      "what a site is worth with no buildings on it, at its best permitted use. It comes from location, nature and the community around it, not from the owner's work.",
  },
  {
    term: "Land rent",
    definition:
      "the yearly value of using a site, before buildings. It is what the land would let for each year.",
  },
  {
    term: "Location value",
    definition:
      "the part of land value that comes from where a site is, such as access to jobs, transport and services.",
  },
  {
    term: "Annual Ground Rent",
    definition:
      "the yearly rental value of a site, created by nature and by the community around it, not by the owner. It is the same thing as land rent.",
  },
  {
    term: "market",
    chip: "(chip: Market)",
    definition: "a value built from observed local sale prices.",
  },
  {
    term: "proxy",
    chip: "(chip: Modelled)",
    definition:
      "a value estimated by the model where local prices are thin or withheld.",
  },
  {
    term: "Estimate",
    chip: "(chip: Estimate)",
    definition:
      "a value for something with no market price, such as peat holding carbon. It is shown for information only, and never added to other figures.",
  },
  {
    term: "Best permitted use",
    definition:
      "the most valuable use the planning rules and physical limits allow. Land is valued at this use, not at whatever it happens to be used for now.",
  },
  {
    term: "Constraint",
    definition:
      "a limit on use, such as a nature designation, flood risk or crofting tenure. A constraint changes the best permitted use and adds no value. It is not an exemption.",
  },
  {
    term: "Residual",
    definition:
      "what remains of a sale price after taking off the depreciated cost of rebuilding the home (allowing for its age). The residual is the land value.",
  },
  {
    term: "Rent rate",
    definition:
      "the yearly share of a land's value used to turn it into a yearly rent. It reflects long-run interest rates, risk and expected growth.",
  },
  {
    term: "Data zone",
    definition:
      "a small official area of about 500 to 1,000 people. The 2011 and 2022 versions are never mixed in one calculation. Data zones are the most detailed level we publish for now. We aim to value each piece of land, step by step, as accurate public data allows.",
  },
  {
    term: "Blocked",
    definition:
      "a figure that may not be shown publicly. Every new figure starts blocked until it passes its checks and is signed off.",
  },
  {
    term: "Research estimate",
    definition:
      "a figure we have worked out from public data. It is a guide, not a bill or an official valuation.",
  },
  {
    term: "Partly estimated",
    definition:
      "a 2022 zone whose value is partly measured and partly modelled.",
  },
  {
    term: "Fully estimated",
    definition:
      "a 2022 zone whose value is entirely modelled. It carries a wider range.",
  },
  {
    term: "Not applicable",
    definition:
      "a zone with no homes, so it has no residential land rent to value. This is not missing data.",
  },
  {
    term: "Common Good land",
    definition:
      "land held by a council for the people of a former burgh. It is valued like any other land, and the community is credited when revenue is shared.",
  },
] as const;

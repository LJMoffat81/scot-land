/**
 * Place-card value/rent rows — labels from RENT_GROUP_NAMES only.
 * FP1 schema on every part: range, unit, confidence, method, class.
 */
import { RENT_GROUP_NAME } from "./rentGroupNames.mjs";

/** Pre-£ range text until modules publish amounts (UX-10 / FP1). */
export const PLACE_CARD_PART_NOT_YET = "not yet estimated";

/** Plain glosses for Parts (UX-10 item 7). */
export const PLACE_CARD_PART_GLOSS = Object.freeze({
  land: "The yearly value of the land under homes.",
  resources: "Rents from things like wind, minerals and fish farming.",
  nature: "Value from nature's services, such as peat holding carbon.",
});

function fp1Fields(classTag) {
  return {
    range: PLACE_CARD_PART_NOT_YET,
    unit: null,
    confidence: null,
    method: null,
    class: classTag,
  };
}

export function defaultAgrGroupRows() {
  return [
    {
      id: "surface",
      label: RENT_GROUP_NAME.land,
      tag: "proxy",
      status: "in_progress",
      applies: true,
      gloss: PLACE_CARD_PART_GLOSS.land,
      ...fp1Fields("proxy"),
      of_which: [
        { id: "planning_uplift", label: "of which: planning uplift" },
      ],
    },
    {
      id: "resource",
      label: RENT_GROUP_NAME.resources,
      tag: "market",
      status: "coming_soon",
      applies: true,
      gloss: PLACE_CARD_PART_GLOSS.resources,
      ...fp1Fields("market"),
    },
    {
      id: "nature",
      label: RENT_GROUP_NAME.nature,
      tag: "shadow",
      status: "coming_soon",
      applies: true,
      gloss: PLACE_CARD_PART_GLOSS.nature,
      ...fp1Fields("shadow"),
    },
  ];
}

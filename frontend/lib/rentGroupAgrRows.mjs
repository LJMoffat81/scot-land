/**
 * Place-card value/rent rows — labels from RENT_GROUP_NAMES only.
 */
import { RENT_GROUP_NAME } from "./rentGroupNames.mjs";

export function defaultAgrGroupRows() {
  return [
    {
      id: "surface",
      label: RENT_GROUP_NAME.land,
      tag: "proxy",
      status: "in_progress",
      applies: true,
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
    },
    {
      id: "nature",
      label: RENT_GROUP_NAME.nature,
      tag: "shadow",
      status: "coming_soon",
      applies: true,
    },
  ];
}

/**
 * Typed re-export of the runtime constant in rentGroupNames.mjs.
 * Prefer importing from here in TS; tests may import the .mjs directly.
 */

import {
  RENT_GROUP_NAME as _RENT_GROUP_NAME,
  RENT_GROUP_NAMES as _RENT_GROUP_NAMES,
} from "./rentGroupNames.mjs";

export const RENT_GROUP_NAMES = _RENT_GROUP_NAMES as readonly [
  "Land",
  "Natural resource rents",
  "Services of nature",
];

export type RentGroupName = (typeof RENT_GROUP_NAMES)[number];

export const RENT_GROUP_NAME = _RENT_GROUP_NAME as {
  readonly land: RentGroupName;
  readonly resources: RentGroupName;
  readonly nature: RentGroupName;
};

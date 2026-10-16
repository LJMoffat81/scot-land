/**
 * RENTS-1 Part 2 — “What we aim to cover”.
 * One list, shared by /roadmap and the Layers panel. Do not copy it elsewhere.
 *
 * Live only when the public site shows that rent. Amounts are withheld, and the
 * working map layers (wind, seabed leases, oil fields, council fill) are context
 * with no rent figure — so none are Live.
 * In progress: the place card already covers homes, or a live Layers switch
 * paints that subject today.
 * Later: parked after the current homes work, or a breakdown the card does not show.
 * `parked` rows stay on the roadmap and are omitted from the Layers panel
 * (business land, licences, spectrum).
 */

export type AimStatus = "Live" | "In progress" | "Not started" | "Later";

export type AimGroupId = "land" | "resources" | "nature";

export type AimRow = {
  /** Fragment on /roadmap and the Layers placeholder link. */
  id: string;
  name: string;
  plain: string;
  status: AimStatus;
  /** Kept on the roadmap. Not listed under LAND. */
  parked?: boolean;
};

export type AimGroup = {
  id: AimGroupId;
  heading: string;
  rows: readonly AimRow[];
};

export const AIM_TO_COVER: readonly AimGroup[] = [
  {
    id: "land",
    heading: "Land (Annual Ground Rent)",
    rows: [
      {
        id: "site-rent-homes",
        name: "Site rent: homes",
        plain:
          "Yearly rental value of the land under homes, without the buildings.",
        status: "In progress",
      },
      {
        id: "site-rent-business",
        name: "Site rent: business",
        plain:
          "Yearly rental value of the land under shops, offices and works.",
        status: "Later",
        parked: true,
      },
      {
        id: "rural-and-farmland-values",
        name: "Rural and farmland values",
        plain:
          "Homes rarely sell in the countryside, so house-sale methods don't work there. We will use published farmland price and rent surveys, plus land capability (soil) maps.",
        status: "Later",
      },
      {
        id: "planning-uplift",
        name: "Planning uplift",
        plain:
          "Extra value land gains from planning permission. It sits inside the land rent and is not added again.",
        status: "Not started",
      },
      {
        id: "infrastructure-commons-uplift",
        name: "Infrastructure commons uplift",
        plain:
          "Land value created by public spending on roads, rail and services. It sits inside the land rent and is not added again.",
        status: "Later",
      },
      {
        id: "licences-and-franchises",
        name: "Licences and franchises",
        plain:
          "Value of exclusive rights granted by government, such as ferry routes, broadcasting and taxi plates.",
        status: "Later",
        parked: true,
      },
      {
        id: "monopoly-and-other-artificial-privileges",
        name: "Monopoly and other artificial privileges",
        plain:
          "Excess return from barriers to entry or a legal privilege.",
        status: "Later",
      },
    ],
  },
  {
    id: "resources",
    heading: "Natural resource rents",
    rows: [
      {
        id: "minerals-and-aggregates",
        name: "Minerals and aggregates",
        plain:
          "Royalty for each tonne of stone, sand, gravel or coal taken from the ground.",
        status: "Not started",
      },
      {
        id: "oil-and-gas",
        name: "Oil and gas",
        plain:
          "Rent from oil and gas fields beyond what extraction costs plus a normal return.",
        status: "In progress",
      },
      {
        id: "water-abstraction",
        name: "Water abstraction",
        plain:
          "Value of taking water from rivers, lochs and the ground under licence.",
        status: "Not started",
      },
      {
        id: "fishing-quota",
        name: "Fishing quota",
        plain: "Value of the right to catch a share of fish stocks.",
        status: "Not started",
      },
      {
        id: "fish-farm-seabed-leases",
        name: "Fish-farm seabed leases",
        plain:
          "Rent for fish farm sites on the seabed, beyond the lease paid to Crown Estate Scotland.",
        status: "Not started",
      },
      {
        id: "onshore-wind-and-hydro-sites",
        name: "Onshore wind and hydro sites",
        plain:
          "Extra rent a wind or hydro site earns over ordinary land rent on the same ground.",
        status: "In progress",
      },
      {
        id: "offshore-wind-and-seabed",
        name: "Offshore wind and seabed",
        plain:
          "Rent for seabed and foreshore used for wind farms, cables and moorings.",
        status: "In progress",
      },
      {
        id: "timber",
        name: "Timber",
        plain:
          "Value of the standing trees' site, beyond planting and management costs.",
        status: "Not started",
      },
      {
        id: "radio-spectrum",
        name: "Radio spectrum",
        plain: "Value of the right to use radio frequencies.",
        status: "Later",
        parked: true,
      },
      {
        id: "orbits-and-airspace",
        name: "Orbits and airspace",
        plain: "Value of orbital slots and airspace rights.",
        status: "Later",
      },
    ],
  },
  {
    id: "nature",
    heading: "Services of nature",
    rows: [
      {
        id: "carbon-in-peat-and-soils",
        name: "Carbon in peat and soils",
        plain:
          "Value of carbon kept in the ground by peat and soils, where there is no market price.",
        status: "Not started",
      },
      {
        id: "flood-regulation-pollination-clean-water-recreation",
        name: "Flood regulation, pollination, clean water, recreation",
        plain: "Other free services of nature.",
        status: "Not started",
      },
    ],
  },
];

/** Layers panel tag. Later and Not started are shown as Coming later. */
export function aimStatusPanelTag(status: AimStatus): string {
  switch (status) {
    case "Later":
      return "Coming later";
    case "In progress":
      return "In progress";
    case "Not started":
      return "Coming later";
    case "Live":
      return "Live";
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

/**
 * Last roadmap row. Not a Layers placeholder (parked so the panel omits it).
 * Status Later — the file had no matching entry.
 */
export const ROADMAP_FINAL_ROW: AimRow = {
  id: "scotland-national-wealth-engine",
  name: "Scotland National Wealth Engine: land value for every parcel, ready to support fair land taxation",
  plain: "",
  status: "Later",
  parked: true,
};

/** Non-parked rows for one LAND sub-group, in roadmap order. */
export function layersPanelAimRows(groupId: AimGroupId): readonly AimRow[] {
  const group = AIM_TO_COVER.find((entry) => entry.id === groupId);
  if (!group) return [];
  return group.rows.filter((row) => !row.parked);
}

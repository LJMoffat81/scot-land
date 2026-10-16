/**
 * LAYERS-ADD-2 public credits and coverage legend.
 * Switches stay off this list until a layer has loaded data.
 */

export const NO_OPEN_DATA_LABEL = "no open data";
export const NO_OPEN_DATA_FILL = "#bdbdbd";

export const LAYERS_ADD2_CREDITS: Record<
  string,
  { label: string; attribution: string; licenceUrl: string }
> = {
  epc_domestic: {
    label: "Domestic energy certificates",
    attribution:
      "Contains public sector information licensed under the Open Government Licence v3.0.",
    licenceUrl:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  },
  ofcom_cn_fixed: {
    label: "Broadband",
    attribution: "Contains Ofcom data © Ofcom 2025",
    licenceUrl:
      "https://www.ofcom.org.uk/phones-and-broadband/coverage-and-speeds/connected-nations-20252/data-downloads-2025",
  },
  nrs_dz_pop_hh: {
    label: "Population and households",
    attribution:
      "Contains National Records of Scotland data licensed under the Open Government Licence v3.0.",
    licenceUrl:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  },
  sg_urban_rural: {
    label: "Town and country",
    attribution:
      "Copyright Scottish Government, contains Ordnance Survey data © Crown copyright and database right 2026.",
    licenceUrl:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  },
  os_open_roads: {
    label: "Roads",
    attribution: "Contains OS data © Crown copyright and database right 2026",
    licenceUrl:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  },
  os_open_greenspace: {
    label: "Parks and green spaces",
    attribution: "Contains OS data © Crown copyright and database right 2026",
    licenceUrl:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  },
  os_open_rivers: {
    label: "Rivers",
    attribution: "Contains OS data © Crown copyright and database right 2026",
    licenceUrl:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  },
  fls_estate: {
    label: "Public forests and land",
    attribution:
      "Contains Forestry and Land Scotland data and OS data © Crown copyright and database right 2026, licensed under the Open Government Licence v3.0.",
    licenceUrl:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  },
  ces_assets: {
    label: "Crown Estate Scotland assets",
    attribution:
      "Contains information from the Crown Estate Scotland licensed under the Open Government Licence v3.0.",
    licenceUrl:
      "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  },
};

export function layersAdd2Credit(layerId: string): string | null {
  return LAYERS_ADD2_CREDITS[layerId]?.attribution ?? null;
}

/** Uncovered councils render grey. They are never labelled as having no allocation. */
export function coverageLegend(
  coverage: "covered" | "uncovered",
  siteCountLabel: string | null,
): { label: string; fill: string } {
  if (coverage === "uncovered") {
    return { label: NO_OPEN_DATA_LABEL, fill: NO_OPEN_DATA_FILL };
  }
  return { label: siteCountLabel ?? "0", fill: "#2e7d32" };
}

export function assertFreeStyleUrl(url: string): void {
  const lower = url.toLowerCase();
  if (
    lower.includes("key=") ||
    lower.includes("api_key") ||
    lower.includes("access_token")
  ) {
    throw new Error("keyed tile endpoint");
  }
}

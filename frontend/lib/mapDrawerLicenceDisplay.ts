/**
 * Display licences for the map Layers drawer.
 * Never surface "research estimate" on a Licence: line — only real licences.
 */

const OGL_V3_LABEL = "Open Government Licence v3.0";
const OGL_V3_URL =
  "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/";

export type DrawerLicenceDisplay = {
  label: string;
  url?: string;
};

/** Per-id overrides when the curated drawer string is not a publishable licence name. */
const LICENCE_BY_ID: Record<string, DrawerLicenceDisplay> = {
  "1": { label: OGL_V3_LABEL, url: OGL_V3_URL },
  "1a": { label: OGL_V3_LABEL, url: OGL_V3_URL },
  "2": { label: OGL_V3_LABEL, url: OGL_V3_URL },
  "6": { label: OGL_V3_LABEL, url: OGL_V3_URL },
  "7": { label: OGL_V3_LABEL, url: OGL_V3_URL },
  "8": { label: OGL_V3_LABEL, url: OGL_V3_URL },
  "9": {
    label: "North Sea Transition Authority open data (non-commercial reuse)",
    url: "https://www.nstauthority.co.uk/data-and-insights/",
  },
  "10": { label: OGL_V3_LABEL, url: OGL_V3_URL },
  vdl: { label: OGL_V3_LABEL, url: OGL_V3_URL },
  "3": { label: OGL_V3_LABEL, url: OGL_V3_URL },
  "4": { label: OGL_V3_LABEL, url: OGL_V3_URL },
  "5": { label: OGL_V3_LABEL, url: OGL_V3_URL },
  designations: { label: OGL_V3_LABEL, url: OGL_V3_URL },
  flood: { label: OGL_V3_LABEL, url: OGL_V3_URL },
  crofting: { label: OGL_V3_LABEL, url: OGL_V3_URL },
  boundaries: { label: OGL_V3_LABEL, url: OGL_V3_URL },
  data_zones: { label: OGL_V3_LABEL, url: OGL_V3_URL },
  builtup_mask: { label: OGL_V3_LABEL, url: OGL_V3_URL },
};

/** True when a drawer licence display is the Open Government Licence. */
export function isOpenGovernmentLicenceDisplay(
  display: DrawerLicenceDisplay,
): boolean {
  const label = display.label.trim();
  return (
    /open government licence/i.test(label) ||
    /^OGL(-|\s)?3(\.0)?$/i.test(label) ||
    /^OGL$/i.test(label)
  );
}

export const DRAWER_OGL_V3: DrawerLicenceDisplay = {
  label: OGL_V3_LABEL,
  url: OGL_V3_URL,
};

function expandKnownAbbreviation(
  licence: string,
  licenceUrl?: string,
): DrawerLicenceDisplay | null {
  const trimmed = licence.trim();
  if (/^OGL(-|\s)?3(\.0)?$/i.test(trimmed) || /^OGL$/i.test(trimmed)) {
    return { label: OGL_V3_LABEL, url: licenceUrl || OGL_V3_URL };
  }
  if (/^non-commercial$/i.test(trimmed)) {
    return {
      label: "Non-commercial open data licence (see source)",
      url: licenceUrl,
    };
  }
  if (/open government licence/i.test(trimmed)) {
    return { label: trimmed, url: licenceUrl || OGL_V3_URL };
  }
  return null;
}

function isResearchEstimateLicence(licence: string): boolean {
  return /research\s*estimate/i.test(licence);
}

/**
 * Licence shown on a Layers drawer row. Prefer a real licence name over
 * placeholder "research estimate" copy from the curated group list.
 */
export function mapDrawerLicenceDisplay(
  id: string,
  licence: string,
  licenceUrl?: string,
): DrawerLicenceDisplay {
  const byId = LICENCE_BY_ID[id];
  if (byId) return { ...byId };

  if (isResearchEstimateLicence(licence)) {
    return { label: OGL_V3_LABEL, url: licenceUrl || OGL_V3_URL };
  }

  const expanded = expandKnownAbbreviation(licence, licenceUrl);
  if (expanded) return expanded;

  const label = licence.trim() || OGL_V3_LABEL;
  return { label, url: licenceUrl };
}

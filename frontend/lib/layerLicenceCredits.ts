/**
 * Static licence-credit list for Methodology and other About surfaces.
 * Every known catalog layer id in LAYER_ATTRIBUTION gets a credit line.
 * Never invents rent £ figures.
 */

import { LAYER_ATTRIBUTION } from "@/lib/layerCatalog";
import {
  isNonCommercialLicence,
  type MapCreditEntry,
} from "@/lib/mapLicenceCredits";

/** One credit row per known layer attribution entry, sorted by label. */
export function allLayerLicenceCredits(): MapCreditEntry[] {
  const entries = Object.entries(LAYER_ATTRIBUTION).map(([layerId, meta]) => {
    const attribution = `${meta.source} — ${meta.licence}`;
    return {
      layerId,
      label: meta.source,
      licence: meta.licence,
      licenceUrl: meta.sourceUrl,
      attribution,
      nonCommercial: isNonCommercialLicence(meta.licence),
    } satisfies MapCreditEntry;
  });
  return entries.sort((a, b) =>
    a.label.localeCompare(b.label, "en", { sensitivity: "base" }),
  );
}

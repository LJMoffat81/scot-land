/**
 * Static licence-credit list for Methodology and other About surfaces.
 * Every known catalog layer id in LAYER_ATTRIBUTION gets a credit line.
 * Never invents rent £ figures.
 */

import { LAYER_ATTRIBUTION } from "@/lib/layerCatalog";
import { LAYERS_ADD2_CREDITS } from "@/lib/layersAdd2Credits";
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
  for (const [layerId, meta] of Object.entries(LAYERS_ADD2_CREDITS)) {
    entries.push({
      layerId,
      label: meta.label,
      licence: "OGL-3.0",
      licenceUrl: meta.licenceUrl,
      attribution: meta.attribution,
      nonCommercial: isNonCommercialLicence(meta.attribution),
    });
  }
  return entries.sort((a, b) =>
    a.label.localeCompare(b.label, "en", { sensitivity: "base" }),
  );
}

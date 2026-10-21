/**
 * Typed re-export of the runtime helpers in esriBasemapKey.mjs.
 * Prefer importing from here in TS; Node strip-types tests may import the .mjs.
 */

export {
  ESRI_BASEMAP_API_KEY_ENV,
  isEsriBasemapKeyConfigured,
  readEsriBasemapApiKey,
} from "./esriBasemapKey.mjs";

export type EsriKeyWindow = Window & {
  __E2E_ESRI_BASEMAP_API_KEY__?: string | null;
};

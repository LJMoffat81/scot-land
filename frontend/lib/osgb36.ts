/**
 * WGS84 (EPSG:4326) → OSGB36 British National Grid (EPSG:27700).
 *
 * Helmert datum shift + Airy 1830 transverse Mercator — matches pyproj
 * EPSG:4326→EPSG:27700 (without OSTN15 grid) to well within ±50 m onshore.
 */

const A_WGS84 = 6_378_137.0;
const B_WGS84 = 6_356_752.3142;
const A_AIRY = 6_377_563.396;
const B_AIRY = 6_356_256.909;
const F0 = 0.999_601_271_7;
const LAT0 = (49 * Math.PI) / 180;
const LON0 = (-2 * Math.PI) / 180;
const E0 = 400_000.0;
const N0 = -100_000.0;

const E2_WGS = 1 - (B_WGS84 * B_WGS84) / (A_WGS84 * A_WGS84);
const E2_AIRY = 1 - (B_AIRY * B_AIRY) / (A_AIRY * A_AIRY);
const N_AIRY = (A_AIRY - B_AIRY) / (A_AIRY + B_AIRY);

/** Helmert WGS84 → OSGB36 (metres, radians, scale). */
const TX = -446.448;
const TY = 125.157;
const TZ = -542.06;
const RX = ((-0.1502 / 3600) * Math.PI) / 180;
const RY = ((-0.247 / 3600) * Math.PI) / 180;
const RZ = ((-0.8421 / 3600) * Math.PI) / 180;
const S = 20.4894e-6;

function wgs84ToOsgb36LatLon(
  latDeg: number,
  lonDeg: number,
): { lat: number; lon: number } {
  const lat = (latDeg * Math.PI) / 180;
  const lon = (lonDeg * Math.PI) / 180;
  const sinLat = Math.sin(lat);
  const cosLat = Math.cos(lat);
  const nu = A_WGS84 / Math.sqrt(1 - E2_WGS * sinLat * sinLat);
  const x = nu * cosLat * Math.cos(lon);
  const y = nu * cosLat * Math.sin(lon);
  const z = (1 - E2_WGS) * nu * sinLat;

  const xp = TX + (1 + S) * x + -RZ * y + RY * z;
  const yp = TY + RZ * x + (1 + S) * y + -RX * z;
  const zp = TZ + -RY * x + RX * y + (1 + S) * z;

  const p = Math.hypot(xp, yp);
  let lat2 = Math.atan2(zp, p * (1 - E2_AIRY));
  for (let i = 0; i < 10; i += 1) {
    const sin2 = Math.sin(lat2);
    const nu2 = A_AIRY / Math.sqrt(1 - E2_AIRY * sin2 * sin2);
    lat2 = Math.atan2(zp + E2_AIRY * nu2 * sin2, p);
  }
  return { lat: (lat2 * 180) / Math.PI, lon: (Math.atan2(yp, xp) * 180) / Math.PI };
}

function osgb36LatLonToGrid(
  latDeg: number,
  lonDeg: number,
): { easting: number; northing: number } {
  const lat = (latDeg * Math.PI) / 180;
  const lon = (lonDeg * Math.PI) / 180;
  const sinLat = Math.sin(lat);
  const cosLat = Math.cos(lat);
  const tanLat = Math.tan(lat);
  const nu = (A_AIRY * F0) / Math.sqrt(1 - E2_AIRY * sinLat * sinLat);
  const rho =
    (A_AIRY * F0 * (1 - E2_AIRY)) /
    (1 - E2_AIRY * sinLat * sinLat) ** 1.5;
  const eta2 = nu / rho - 1;
  const n = N_AIRY;
  const Ma =
    (1 + n + (5 / 4) * n ** 2 + (5 / 4) * n ** 3) * (lat - LAT0);
  const Mb =
    (3 * n + 3 * n ** 2 + (21 / 8) * n ** 3) *
    Math.sin(lat - LAT0) *
    Math.cos(lat + LAT0);
  const Mc =
    ((15 / 8) * n ** 2 + (15 / 8) * n ** 3) *
    Math.sin(2 * (lat - LAT0)) *
    Math.cos(2 * (lat + LAT0));
  const Md =
    ((35 / 24) * n ** 3) *
    Math.sin(3 * (lat - LAT0)) *
    Math.cos(3 * (lat + LAT0));
  const M = B_AIRY * F0 * (Ma - Mb + Mc - Md);
  const I = M + N0;
  const II = (nu / 2) * sinLat * cosLat;
  const III =
    (nu / 24) * sinLat * cosLat ** 3 * (5 - tanLat ** 2 + 9 * eta2);
  const IIIA =
    (nu / 720) *
    sinLat *
    cosLat ** 5 *
    (61 - 58 * tanLat ** 2 + tanLat ** 4);
  const IV = nu * cosLat;
  const V = (nu / 6) * cosLat ** 3 * (nu / rho - tanLat ** 2);
  const VI =
    (nu / 120) *
    cosLat ** 5 *
    (5 -
      18 * tanLat ** 2 +
      tanLat ** 4 +
      14 * eta2 -
      58 * tanLat ** 2 * eta2);
  const dLon = lon - LON0;
  const northing = I + II * dLon ** 2 + III * dLon ** 4 + IIIA * dLon ** 6;
  const easting = E0 + IV * dLon + V * dLon ** 3 + VI * dLon ** 5;
  return { easting, northing };
}

/** British National Grid easting/northing (metres) for a WGS84 point. */
export function wgs84ToOsgb36(
  lat: number,
  lng: number,
): { easting: number; northing: number } {
  const osgb = wgs84ToOsgb36LatLon(lat, lng);
  return osgb36LatLonToGrid(osgb.lat, osgb.lon);
}

/**
 * Map reference string: `easting,northing` (metres, rounded), EPSG:27700.
 * Never a what3words brand string.
 */
export function osgb36MapReference(lat: number, lng: number): string {
  const { easting, northing } = wgs84ToOsgb36(lat, lng);
  return `${Math.round(easting)},${Math.round(northing)}`;
}

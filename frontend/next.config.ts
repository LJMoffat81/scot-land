import type { NextConfig } from "next";

// Next injects inline bootstrap scripts and the UI sets style attributes.
// A per-request nonce would need another file, so those two stay 'unsafe-inline'.
// MapLibre's worker is a blob URL, and raster tiles are images (data: and blob: too).
// Outside hosts the browser actually fetches: OpenFreeMap (style, tiles, sprites,
// glyphs) and Esri World Imagery. Context and parcel tiles are same-origin proxies.
// API docs at /developers/api use self-hosted swagger-ui under /swagger-ui/ — no CDN.
const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "form-action 'self'",
  "frame-ancestors 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://tiles.openfreemap.org https://server.arcgisonline.com",
  "font-src 'self'",
  "connect-src 'self' https://tiles.openfreemap.org https://server.arcgisonline.com http://localhost:* http://127.0.0.1:* https://localhost:* https://127.0.0.1:* ws://localhost:* ws://127.0.0.1:* wss://localhost:* wss://127.0.0.1:*",
  "worker-src 'self' blob:",
  "child-src 'self' blob:",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  poweredByHeader: false,
  // Expose PARCELS_PUBLIC to client bundles (default false). Only "true" enables
  // parcel tile proxy routes and the Land parcels layer toggle.
  env: {
    PARCELS_PUBLIC: process.env.PARCELS_PUBLIC ?? "false",
  },
  // Next 16 blocks HMR/dev assets when the page is opened on a different host
  // (localhost vs 127.0.0.1). Allow both so local browsing does not break.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async redirects() {
    return [
      // Site rewrite PR1 — permanent redirects (spec A).
      {
        source: "/downloads",
        destination: "/developers?moved=1#downloads",
        permanent: true,
      },
      {
        source: "/open-api",
        destination: "/developers?moved=1#api",
        permanent: true,
      },
      // Charter C1+C2: docs entry points land on self-hosted Swagger.
      {
        source: "/docs",
        destination: "/developers/api",
        statusCode: 301,
      },
      {
        source: "/backend/docs",
        destination: "/developers/api",
        statusCode: 301,
      },
      {
        source: "/backend/docs/:path*",
        destination: "/developers/api",
        statusCode: 301,
      },
      {
        source: "/mission",
        destination: "/about",
        permanent: true,
      },
    ];
  },
  async headers() {
    // HOME-TUNNEL: long cache for hashed Next assets and public static files.
    const longImmutable = [
      { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
    ];
    const longStatic = [
      { key: "Cache-Control", value: "public, max-age=86400" },
    ];
    return [
      { source: "/:path*", headers: securityHeaders },
      { source: "/_next/static/:path*", headers: longImmutable },
      { source: "/scot-land-mark.png", headers: longStatic },
      { source: "/swagger-ui/:path*", headers: longStatic },
      // Site rewrite PR3 item 5 — packaged downloads force save-as.
      // manifest.json is excluded so the developers page can fetch it as JSON.
      {
        source: "/downloads/:file*.csv",
        headers: [
          { key: "Content-Disposition", value: "attachment" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
      {
        source: "/downloads/:file*.geojson",
        headers: [
          { key: "Content-Disposition", value: "attachment" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
      {
        source: "/downloads/:file*.zip",
        headers: [
          { key: "Content-Disposition", value: "attachment" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
  // API proxy is app/backend/[...path]/route.ts (not rewrites).
  // Rewrites surface socket hang-ups as TypeError: Failed to fetch;
  // the route handler returns clean JSON 503 instead.
};

export default nextConfig;

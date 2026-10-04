import type { NextConfig } from "next";

// Next injects inline bootstrap scripts and the UI sets style attributes.
// A per-request nonce would need another file, so those two stay 'unsafe-inline'.
// MapLibre's worker is a blob URL, and raster tiles are images (data: and blob: too).
// Outside hosts the browser actually fetches: OpenFreeMap (style, tiles, sprites,
// glyphs) and Esri World Imagery. Context and parcel tiles are same-origin proxies.
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
  // Next 16 blocks HMR/dev assets when the page is opened on a different host
  // (localhost vs 127.0.0.1). Allow both so local browsing does not break.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async headers() {
    return [
      { source: "/", headers: securityHeaders },
      { source: "/:path*", headers: securityHeaders },
    ];
  },
  // API proxy is app/backend/[...path]/route.ts (not rewrites).
  // Rewrites surface socket hang-ups as TypeError: Failed to fetch;
  // the route handler returns clean JSON 503 instead.
};

export default nextConfig;

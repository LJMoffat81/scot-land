import type { Metadata } from "next";
import localFont from "next/font/local";

import {
  absoluteOgImageUrl,
  getMetadataBase,
  OG_IMAGES,
} from "@/lib/socialMeta";

import "./globals.css";
import "./platform.css";
import "./map-chrome.css";

const mona = localFont({
  src: "../node_modules/@fontsource-variable/mona-sans/files/mona-sans-latin-wght-normal.woff2",
  weight: "200 900",
  display: "swap",
  fallback: ["Segoe UI", "Helvetica", "Arial", "sans-serif"],
});

const SITE_DESCRIPTION =
  "Search a Scottish postcode, place or map reference on an open land map. Research estimate — land rent figures are not published yet.";
const OG_DESCRIPTION =
  "Find a place on Scotland’s open land map. Research estimate — land rent figures are not published yet.";

export const metadata: Metadata = {
  metadataBase: getMetadataBase(),
  title: "Map | Scot-LAND",
  description: SITE_DESCRIPTION,
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  manifest: "/site.webmanifest",
  openGraph: {
    title: "Map | Scot-LAND",
    description: OG_DESCRIPTION,
    images: [...OG_IMAGES],
  },
  twitter: {
    card: "summary_large_image",
    title: "Map | Scot-LAND",
    description: OG_DESCRIPTION,
    images: [absoluteOgImageUrl()],
  },
};

/** Patch SwaggerUIBundle so validatorUrl is always null (no validator.swagger.io). */
const SWAGGER_VALIDATOR_NULL_PATCH = `(function(){var b;Object.defineProperty(window,"SwaggerUIBundle",{configurable:true,enumerable:true,get:function(){return b;},set:function(fn){if(typeof fn!=="function"){b=fn;return;}function w(opts){var o=Object.assign({},opts||{},{validatorUrl:null});return fn(o);}try{Object.assign(w,fn);}catch(e){}w.presets=fn.presets;w.plugins=fn.plugins;b=w;}});})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={mona.className}>
        <script
          dangerouslySetInnerHTML={{ __html: SWAGGER_VALIDATOR_NULL_PATCH }}
        />
        {children}
      </body>
    </html>
  );
}

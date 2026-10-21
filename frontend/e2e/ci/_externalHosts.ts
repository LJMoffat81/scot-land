/**
 * CI-DEDUP-1b — exact-host external stubs + strict console gate.
 * Match on hostname equality only (never regex / suffix).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { BrowserContext, Page, Route } from "@playwright/test";

/** Frozen exact list. Additions need a signed-off spec change. */
export const EXTERNAL_HOSTS = Object.freeze([
  "tiles.openfreemap.org",
  "basemapstyles-api.arcgis.com",
  "ibasemaps-api.arcgis.com",
  "basemaps-api.arcgis.com",
  "cdn.arcgis.com",
  "www.arcgis.com",
] as const);

export type ExternalHost = (typeof EXTERNAL_HOSTS)[number];

const ABORT_EXACT = "AbortError: The user aborted a request.";

const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

/** Empty-but-valid glyph/sprite-ish protobuf (same bytes as map-cards helper). */
const EMPTY_GLYPH_PBF = Buffer.from(
  "ChoKEU9wZW4gU2FucyBSZWd1bGFyEgUwLTI1NQ==",
  "base64",
);

function styleFixtureBody(): string {
  return readFileSync(
    join(process.cwd(), "e2e", "fixtures", "esri-imagery-style.json"),
    "utf8",
  );
}

function isExternalHost(hostname: string): hostname is ExternalHost {
  return (EXTERNAL_HOSTS as readonly string[]).includes(hostname);
}

export type ExternalHostStub = {
  /** Per-hostname fulfilled request counts. */
  hits: Record<string, number>;
};

/**
 * Route listed hosts only. Style JSON / PNG tiles / glyph-sprite / else 204.
 */
export async function stubExternalHosts(
  context: BrowserContext,
): Promise<ExternalHostStub> {
  const hits: Record<string, number> = Object.fromEntries(
    EXTERNAL_HOSTS.map((h) => [h, 0]),
  );
  const styleBody = styleFixtureBody();

  await context.route(
    (url) => {
      try {
        return isExternalHost(new URL(url).hostname);
      } catch {
        return false;
      }
    },
    async (route: Route) => {
      const reqUrl = route.request().url();
      let hostname = "";
      let pathname = "";
      try {
        const u = new URL(reqUrl);
        hostname = u.hostname;
        pathname = u.pathname;
      } catch {
        await route.fulfill({ status: 204 });
        return;
      }
      if (!isExternalHost(hostname)) {
        await route.continue();
        return;
      }
      hits[hostname] = (hits[hostname] ?? 0) + 1;

      const lower = `${pathname}${reqUrl}`.toLowerCase();
      // Style JSON (Esri basemapstyles / .json style docs)
      if (
        /\/styles\//i.test(pathname) ||
        /style\.json$/i.test(pathname) ||
        (hostname === "basemapstyles-api.arcgis.com" &&
          /\.json($|\?)/i.test(pathname))
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: styleBody,
        });
        return;
      }
      // Raster / tile image bytes
      if (
        /\.(png|jpe?g|webp|gif)($|\?)/i.test(pathname) ||
        /\/tile\//i.test(pathname) ||
        /\/tiles\//i.test(pathname) ||
        /\/MapServer\/tile\//i.test(pathname)
      ) {
        await route.fulfill({
          status: 200,
          contentType: "image/png",
          body: TINY_PNG,
        });
        return;
      }
      // Glyphs / sprites / fonts
      if (
        /glyph|font|sprite|\.pbf/i.test(lower) ||
        /\/fonts\//i.test(pathname)
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/x-protobuf",
          body: EMPTY_GLYPH_PBF,
        });
        return;
      }
      await route.fulfill({ status: 204 });
    },
  );

  return { hits };
}

export type RecordedError = { text: string; url: string };

export type StrictConsoleGate = {
  errors: RecordedError[];
  assertClean: () => void;
};

/**
 * Strict console gate: same-origin errors never filtered by status code.
 * Ignores only EXTERNAL_HOSTS location hosts, or the exact Playwright abort text.
 */
export function attachStrictConsoleGate(page: Page): StrictConsoleGate {
  const errors: RecordedError[] = [];

  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const loc = msg.location();
    errors.push({ text: msg.text(), url: loc?.url ?? "" });
  });
  page.on("pageerror", (err) => {
    errors.push({ text: String(err), url: page.url() });
  });

  return {
    errors,
    assertClean() {
      const app = errors.filter((e) => {
        if (e.text === ABORT_EXACT) return false;
        if (!e.url) return true;
        try {
          const host = new URL(e.url).hostname;
          if (isExternalHost(host)) return false;
        } catch {
          // relative / invalid URL → treat as app
        }
        return true;
      });
      if (app.length > 0) {
        throw new Error(
          `CONSOLE_GATE: expected 0 app errors, got ${app.length}: ${app[0]!.text}`,
        );
      }
    },
  };
}

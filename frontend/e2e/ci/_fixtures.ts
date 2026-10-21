/**
 * CI-DEDUP-1b — Playwright fixtures for every e2e/ci spec.
 * Auto-applies exact-host stubs + strict console gate (assert on teardown).
 * csp-esri-1: test.use({ stubExternalHostsEnabled: false }).
 * Gate proof specs: test.use({ skipStrictConsoleAssert: true }).
 */
import { test as base, expect, type Page } from "@playwright/test";
import {
  attachStrictConsoleGate,
  stubExternalHosts,
  type ExternalHostStub,
  type StrictConsoleGate,
} from "./_externalHosts";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

/**
 * CI has no FastAPI. Quiet origin backend/gbp so same-origin 503 from the
 * Next rewrite is not mistaken for an app console-gate failure.
 * Spec-registered routes (LIFO) still win for intentional 4xx/5xx cases.
 */
async function stubCiOriginQuiet(page: Page) {
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/health/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    const wantsGeo =
      /\/layers\//i.test(url) ||
      /\/boundaries\//i.test(url) ||
      /\/w3w-grid/i.test(url) ||
      /\/parcels/i.test(url);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(wantsGeo ? EMPTY_FC : {}),
    });
  });
}

type CiDedupFixtures = {
  /** When false, skip EXTERNAL_HOSTS routing (csp-esri-1 observes real CSP). */
  stubExternalHostsEnabled: boolean;
  /** When true, do not call assertClean on teardown (G1/G2 expect errors). */
  skipStrictConsoleAssert: boolean;
  /** Shared stub handle (hit counters) when stubbing is enabled. */
  externalHostStub: ExternalHostStub | null;
  /** Strict gate attached to the page. */
  consoleGate: StrictConsoleGate;
  /** Auto fixture that wires stub + gate for every test. */
  _ciDedup1bAuto: void;
};

export const test = base.extend<CiDedupFixtures>({
  stubExternalHostsEnabled: [true, { option: true }],
  skipStrictConsoleAssert: [false, { option: true }],

  externalHostStub: async ({ context, stubExternalHostsEnabled }, use) => {
    if (!stubExternalHostsEnabled) {
      await use(null);
      return;
    }
    const handle = await stubExternalHosts(context);
    await use(handle);
  },

  consoleGate: async ({ page }, use) => {
    await stubCiOriginQuiet(page);
    const gate = attachStrictConsoleGate(page);
    await use(gate);
  },

  _ciDedup1bAuto: [
    async (
      {
        externalHostStub,
        consoleGate,
        skipStrictConsoleAssert,
      },
      use,
    ) => {
      void externalHostStub;
      await use();
      if (!skipStrictConsoleAssert) {
        consoleGate.assertClean();
      }
    },
    { auto: true },
  ],
});

export { expect };
export type { StrictConsoleGate, ExternalHostStub };

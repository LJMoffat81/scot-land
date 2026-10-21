/**
 * CI-DEDUP-1b — Playwright fixtures for every e2e/ci spec.
 * Auto-applies exact-host stubs + strict console gate (assert on teardown).
 * csp-esri-1: test.use({ stubExternalHostsEnabled: false }).
 * Gate proof specs: test.use({ skipStrictConsoleAssert: true }).
 */
import { test as base, expect } from "@playwright/test";
import {
  attachStrictConsoleGate,
  stubExternalHosts,
  type ExternalHostStub,
  type StrictConsoleGate,
} from "./_externalHosts";

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

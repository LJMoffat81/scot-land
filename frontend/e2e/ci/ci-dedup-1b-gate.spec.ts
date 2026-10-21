/**
 * CI-DEDUP-1b — G1–G6 pins for external-host stub + strict console gate.
 * Runs in the blocking e2e job (auto-discovered).
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./_fixtures";
import {
  EXTERNAL_HOSTS,
  attachStrictConsoleGate,
  stubExternalHosts,
} from "./_externalHosts";

test.describe("CI-DEDUP-1b console gate", () => {
  // Own stubs for G3/G4 hit counters; skip auto assert (G1/G2 expect errors).
  test.use({
    skipStrictConsoleAssert: true,
    stubExternalHostsEnabled: false,
  });

  test("G1 same-origin console.error fails assertClean with exact message", async ({
    page,
  }) => {
    const gate = attachStrictConsoleGate(page);
    await page.goto("about:blank");
    await page.evaluate(() => console.error("APP_ERR_SENTINEL"));
    await expect(async () => gate.assertClean()).rejects.toThrow(
      "CONSOLE_GATE: expected 0 app errors, got 1: APP_ERR_SENTINEL",
    );
  });

  test("G2 same-origin 503 is not filtered", async ({ page, baseURL }) => {
    const gate = attachStrictConsoleGate(page);
    await page.route("**/__e2e_503_probe.json", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: "unavailable" }),
      });
    });
    await page.goto(baseURL || "http://localhost:3100/");
    await page.evaluate(async () => {
      await fetch(`/__e2e_503_probe.json?t=${Date.now()}`);
      console.error("APP_503_SENTINEL");
    });
    await expect(async () => gate.assertClean()).rejects.toThrow(
      /CONSOLE_GATE: expected 0 app errors, got \d+:/,
    );
    const texts = gate.errors.map((e) => e.text).join("\n");
    expect(texts).toMatch(/APP_503_SENTINEL|503/);
  });

  test("G3 listed hosts are stubbed; listed-host console errors ignored", async ({
    context,
    page,
  }) => {
    const stub = await stubExternalHosts(context);
    const gate = attachStrictConsoleGate(page);
    await page.goto("about:blank");

    const basemapHitsBefore = stub.hits["basemaps-api.arcgis.com"] ?? 0;
    const tilesHitsBefore = stub.hits["tiles.openfreemap.org"] ?? 0;

    await page.evaluate(async () => {
      await fetch("https://basemaps-api.arcgis.com/x").catch(() => undefined);
      await fetch("https://tiles.openfreemap.org/x").catch(() => undefined);
    });

    expect(stub.hits["basemaps-api.arcgis.com"] - basemapHitsBefore).toBe(1);
    expect(stub.hits["tiles.openfreemap.org"] - tilesHitsBefore).toBe(1);

    // Inject a console.error whose location is a listed host (overrides stub for this URL).
    await page.route(
      "https://basemaps-api.arcgis.com/__e2e_err.js",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/javascript",
          body: 'console.error("CDN_HOST_ERR");',
        });
      },
    );
    await page.addScriptTag({
      url: "https://basemaps-api.arcgis.com/__e2e_err.js",
    });
    expect(gate.errors.some((e) => e.text.includes("CDN_HOST_ERR"))).toBe(true);
    // Listed-host location → assertClean must pass.
    expect(() => gate.assertClean()).not.toThrow();
  });

  test("G4 unlisted host is not stubbed; its console error counts", async ({
    context,
    page,
  }) => {
    const stub = await stubExternalHosts(context);
    await page.goto("about:blank");
    expect((EXTERNAL_HOSTS as readonly string[]).includes("example.invalid")).toBe(
      false,
    );
    const before = { ...stub.hits };
    // Probe: request an unlisted host — EXTERNAL_HOSTS stub must not increment.
    await page.evaluate(async () => {
      await fetch("https://example.invalid/x").catch(() => undefined);
    });
    for (const h of EXTERNAL_HOSTS) {
      expect(stub.hits[h] ?? 0, h).toBe(before[h] ?? 0);
    }

    // Fresh gate after the probe so DNS noise is not in the assertClean message.
    const gate = attachStrictConsoleGate(page);
    await page.route("https://example.invalid/__e2e_err.js", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/javascript",
        body: 'console.error("UNLISTED_HOST_ERR");',
      });
    });
    await page.addScriptTag({ url: "https://example.invalid/__e2e_err.js" });
    await expect(async () => gate.assertClean()).rejects.toThrow(
      /CONSOLE_GATE: expected 0 app errors, got \d+: UNLISTED_HOST_ERR/,
    );
  });

  test("G5 EXTERNAL_HOSTS is the exact 6-host list", () => {
    expect([...EXTERNAL_HOSTS]).toEqual([
      "tiles.openfreemap.org",
      "basemapstyles-api.arcgis.com",
      "ibasemaps-api.arcgis.com",
      "basemaps-api.arcgis.com",
      "cdn.arcgis.com",
      "www.arcgis.com",
    ]);
  });

  test("G6 no local filterNoise; no /404|503/ console filters in specs", () => {
    const ciDir = join(process.cwd(), "e2e", "ci");
    const offendersFilterNoise: string[] = [];
    const offenders404: string[] = [];
    for (const name of readdirSync(ciDir)) {
      if (!name.endsWith(".spec.ts")) continue;
      // Skip this pin file (it mentions the banned tokens in assertions).
      if (name === "ci-dedup-1b-gate.spec.ts") continue;
      const src = readFileSync(join(ciDir, name), "utf8");
      if (/\bfunction filterNoise\b|\bfilterNoise\s*\(/.test(src)) {
        offendersFilterNoise.push(name);
      }
      if (/\/(?:[^/\n]*?)404\|503(?:[^/\n]*?)\//.test(src)) {
        offenders404.push(name);
      }
    }
    expect(
      offendersFilterNoise,
      `local filterNoise still present: ${offendersFilterNoise.join(", ")}`,
    ).toEqual([]);
    expect(
      offenders404,
      `/404|503/ still present: ${offenders404.join(", ")}`,
    ).toEqual([]);
  });
});

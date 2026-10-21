/**
 * CI-DEDUP-1b-r2 — G/E pins for strict console gate + external-host stubs.
 * Blocking e2e job (auto-discovered).
 */
import { expect, test, EXTERNAL_HOSTS } from "./_fixtures";
import type { Page } from "@playwright/test";
import { attachConsoleGate } from "./_mapCardsHelpers";

const GATE_PREFIX = "**/__e2e_gate/**";

async function serveGatePage(page: Page, html: string) {
  await page.route(GATE_PREFIX, async (route) => {
    const url = route.request().url();
    if (url.includes("/__e2e_gate/missing.json.bak")) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: "{}",
      });
      return;
    }
    if (url.includes("/__e2e_gate/missing.json")) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: '{"error":"missing"}',
      });
      return;
    }
    if (url.includes("/__e2e_gate/unavailable.json")) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: '{"error":"unavailable"}',
      });
      return;
    }
    if (url.includes("/__e2e_gate/page")) {
      await route.fulfill({
        status: 200,
        contentType: "text/html",
        body: html,
      });
      return;
    }
    await route.fulfill({ status: 204 });
  });
}

/** Chromium emits "Failed to load resource" for subresource tags, not fetch(). */
async function loadSubresource(page: Page, path: string) {
  await page.evaluate(async (src) => {
    await new Promise<void>((resolve) => {
      const el = document.createElement("script");
      el.src = src;
      el.onload = () => resolve();
      el.onerror = () => resolve();
      document.head.appendChild(el);
    });
  }, path);
}

test.describe("CI-DEDUP-1b-r2 console gate", () => {
  test("G1 same-origin console.error fails assertClean with exact message", async ({
    page,
    gate,
  }) => {
    await serveGatePage(page, "<!doctype html><html><body>g1</body></html>");
    await page.goto("/__e2e_gate/page");
    await page.evaluate(() => console.error("APP_ERR_SENTINEL"));
    await expect(async () => gate.assertClean()).rejects.toThrow(
      "CONSOLE_GATE: expected 0 app errors, got 1: APP_ERR_SENTINEL",
    );
  });

  test("G2 same-origin 404 is not filtered", async ({ page, gate }) => {
    await serveGatePage(page, "<!doctype html><html><body>g2</body></html>");
    await page.goto("/__e2e_gate/page");
    await loadSubresource(page, `/__e2e_gate/missing.json?t=${Date.now()}`);
    await expect(async () => gate.assertClean()).rejects.toThrow(
      "CONSOLE_GATE: expected 0 app errors, got 1: Failed to load resource: the server responded with a status of 404 (Not Found)",
    );
  });

  test("G2b same-origin 503 is not filtered", async ({ page, gate }) => {
    await serveGatePage(page, "<!doctype html><html><body>g2b</body></html>");
    await page.goto("/__e2e_gate/page");
    await loadSubresource(
      page,
      `/__e2e_gate/unavailable.json?t=${Date.now()}`,
    );
    await expect(async () => gate.assertClean()).rejects.toThrow(
      "CONSOLE_GATE: expected 0 app errors, got 1: Failed to load resource: the server responded with a status of 503 (Service Unavailable)",
    );
  });

  test("G3 listed hosts are stubbed once; listed-host errors ignored", async ({
    page,
    gate,
    hostStub,
  }) => {
    expect(hostStub).not.toBeNull();
    await page.goto("about:blank");
    const beforeBasemap = hostStub!.hits["basemaps-api.arcgis.com"] ?? 0;
    const beforeTiles = hostStub!.hits["tiles.openfreemap.org"] ?? 0;

    await page.evaluate(async () => {
      await fetch("https://basemaps-api.arcgis.com/x").catch(() => undefined);
      await fetch("https://tiles.openfreemap.org/x").catch(() => undefined);
    });

    expect(hostStub!.hits["basemaps-api.arcgis.com"] - beforeBasemap).toBe(1);
    expect(hostStub!.hits["tiles.openfreemap.org"] - beforeTiles).toBe(1);

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
    expect(() => gate.assertClean()).not.toThrow();
  });

  test("G4 unlisted host is not stubbed; its console error counts", async ({
    page,
    gate,
    hostStub,
  }) => {
    expect(hostStub).not.toBeNull();
    await page.goto("about:blank");
    // Fulfil via page.route (not EXTERNAL_HOSTS stub) so DNS does not emit noise.
    let unlistedHits = 0;
    await page.route("https://example.invalid/**", async (route) => {
      unlistedHits += 1;
      const url = route.request().url();
      if (url.includes("__e2e_err.js")) {
        await route.fulfill({
          status: 200,
          contentType: "application/javascript",
          body: 'console.error("UNLISTED_HOST_ERR");',
        });
        return;
      }
      await route.fulfill({ status: 204 });
    });
    const before = { ...hostStub!.hits };
    await page.evaluate(async () => {
      await fetch("https://example.invalid/x").catch(() => undefined);
    });
    for (const h of EXTERNAL_HOSTS) {
      expect(hostStub!.hits[h] ?? 0, h).toBe(before[h] ?? 0);
    }
    expect(unlistedHits).toBe(1);

    await page.addScriptTag({ url: "https://example.invalid/__e2e_err.js" });
    await expect(async () => gate.assertClean()).rejects.toThrow(
      /CONSOLE_GATE: expected 0 app errors, got \d+: UNLISTED_HOST_ERR/,
    );
  });

  test("G4b suffix and bare-domain hosts are not stubbed", async ({
    page,
    hostStub,
  }) => {
    expect(hostStub).not.toBeNull();
    await page.goto("about:blank");
    // Fulfil so probes do not leave net::ERR console noise for teardown.
    await page.route("https://evil-arcgis.com.example.invalid/**", async (route) => {
      await route.fulfill({ status: 204 });
    });
    await page.route("https://arcgis.com/**", async (route) => {
      await route.fulfill({ status: 204 });
    });
    await page.evaluate(async () => {
      await fetch("https://evil-arcgis.com.example.invalid/x").catch(
        () => undefined,
      );
      await fetch("https://arcgis.com/x").catch(() => undefined);
    });
    // EXTERNAL_HOSTS stub must not claim these (exact hostname only).
    expect(
      hostStub!.hits["evil-arcgis.com.example.invalid"] ?? 0,
      "counter expected 0, received 1",
    ).toBe(0);
    expect(
      hostStub!.hits["arcgis.com"] ?? 0,
      "counter expected 0, received 1",
    ).toBe(0);
  });

  test("G5 EXTERNAL_HOSTS is the exact frozen 6-host list", () => {
    expect([...EXTERNAL_HOSTS]).toEqual([
      "tiles.openfreemap.org",
      "basemapstyles-api.arcgis.com",
      "ibasemaps-api.arcgis.com",
      "basemaps-api.arcgis.com",
      "cdn.arcgis.com",
      "www.arcgis.com",
    ]);
    expect(Object.isFrozen(EXTERNAL_HOSTS)).toBe(true);
  });

  test("G6 AbortError exact text only is ignored", async ({ page, gate }) => {
    await page.goto("about:blank");
    await page.evaluate(() =>
      console.error("AbortError: The user aborted a request."),
    );
    expect(() => gate.assertClean()).not.toThrow();

    await page.evaluate(() =>
      console.error("AbortError: The user aborted a request"),
    );
    await expect(async () => gate.assertClean()).rejects.toThrow(
      "CONSOLE_GATE: expected 0 app errors, got 1: AbortError: The user aborted a request",
    );

    await page.evaluate(() =>
      console.error("xAbortError: The user aborted a request."),
    );
    await expect(async () => gate.assertClean()).rejects.toThrow(
      "CONSOLE_GATE: expected 0 app errors, got 1: xAbortError: The user aborted a request.",
    );
  });

  test("E1 expected error present ×1 count 1 passes", async ({ page, gate }) => {
    await serveGatePage(page, "<!doctype html><html><body>e1</body></html>");
    await page.goto("/__e2e_gate/page");
    gate.expectError({
      urlPath: "/__e2e_gate/missing.json",
      status: 404,
      count: 1,
    });
    await loadSubresource(page, `/__e2e_gate/missing.json?t=${Date.now()}`);
    expect(() => gate.assertClean()).not.toThrow();
  });

  test("E2 expected ×1 absent throws", async ({ page, gate }) => {
    await serveGatePage(page, "<!doctype html><html><body>e2</body></html>");
    await page.goto("/__e2e_gate/page");
    gate.expectError({
      urlPath: "/__e2e_gate/missing.json",
      status: 404,
      count: 1,
    });
    await expect(async () => gate.assertClean()).rejects.toThrow(
      'CONSOLE_GATE: expected error "404 /__e2e_gate/missing.json" x1, got 0',
    );
  });

  test("E3 expected ×1 present ×2 throws", async ({ page, gate }) => {
    await serveGatePage(page, "<!doctype html><html><body>e3</body></html>");
    await page.goto("/__e2e_gate/page");
    gate.expectError({
      urlPath: "/__e2e_gate/missing.json",
      status: 404,
      count: 1,
    });
    await loadSubresource(page, `/__e2e_gate/missing.json?t=1`);
    await loadSubresource(page, `/__e2e_gate/missing.json?t=2`);
    await expect(async () => gate.assertClean()).rejects.toThrow(
      'CONSOLE_GATE: expected error "404 /__e2e_gate/missing.json" x1, got 2',
    );
  });

  test("E4 expected ×2 present ×1 throws", async ({ page, gate }) => {
    await serveGatePage(page, "<!doctype html><html><body>e4</body></html>");
    await page.goto("/__e2e_gate/page");
    gate.expectError({
      urlPath: "/__e2e_gate/missing.json",
      status: 404,
      count: 2,
    });
    await loadSubresource(page, `/__e2e_gate/missing.json?t=1`);
    await expect(async () => gate.assertClean()).rejects.toThrow(
      'CONSOLE_GATE: expected error "404 /__e2e_gate/missing.json" x2, got 1',
    );
  });

  test("E5 text match is exact (trailing space fails)", async ({
    page,
    gate,
  }) => {
    await page.goto("about:blank");
    gate.expectError({ text: "APP_ERR_SENTINEL", count: 1 });
    await page.evaluate(() => console.error("APP_ERR_SENTINEL "));
    await expect(async () => gate.assertClean()).rejects.toThrow(
      'CONSOLE_GATE: expected error "APP_ERR_SENTINEL" x1, got 0',
    );
  });

  test("E6 urlPath must match pathname exactly", async ({ page, gate }) => {
    await serveGatePage(page, "<!doctype html><html><body>e6</body></html>");
    await page.goto("/__e2e_gate/page");
    gate.expectError({
      urlPath: "/__e2e_gate/missing.json",
      status: 404,
      count: 1,
    });
    await loadSubresource(
      page,
      `/__e2e_gate/missing.json.bak?t=${Date.now()}`,
    );
    await expect(async () => gate.assertClean()).rejects.toThrow(
      'CONSOLE_GATE: expected error "404 /__e2e_gate/missing.json" x1, got 0',
    );
  });

  test("E7 wrong status does not match", async ({ page, gate }) => {
    await serveGatePage(page, "<!doctype html><html><body>e7</body></html>");
    await page.goto("/__e2e_gate/page");
    gate.expectError({
      urlPath: "/__e2e_gate/unavailable.json",
      status: 404,
      count: 1,
    });
    await loadSubresource(
      page,
      `/__e2e_gate/unavailable.json?t=${Date.now()}`,
    );
    await expect(async () => gate.assertClean()).rejects.toThrow(
      'CONSOLE_GATE: expected error "404 /__e2e_gate/unavailable.json" x1, got 0',
    );
  });

  test("E8 expectError does not swallow unrelated errors", async ({
    page,
    gate,
  }) => {
    await serveGatePage(page, "<!doctype html><html><body>e8</body></html>");
    await page.goto("/__e2e_gate/page");
    gate.expectError({
      urlPath: "/__e2e_gate/missing.json",
      status: 404,
      count: 1,
    });
    await loadSubresource(page, `/__e2e_gate/missing.json?t=${Date.now()}`);
    await page.evaluate(() => console.error("OTHER"));
    await expect(async () => gate.assertClean()).rejects.toThrow(
      "CONSOLE_GATE: expected 0 app errors, got 1: OTHER",
    );
  });

  test("E9 expectError validation messages", ({ gate }) => {
    expect(() =>
      gate.expectError({ text: /x/ as unknown as string, count: 1 }),
    ).toThrow("CONSOLE_GATE: expectError takes an exact string, not a RegExp");
    expect(() => gate.expectError({ text: "", count: 1 })).toThrow(
      "CONSOLE_GATE: expectError needs a non-empty text or urlPath",
    );
    expect(() => gate.expectError({ text: "  ", count: 1 })).toThrow(
      "CONSOLE_GATE: expectError needs a non-empty text or urlPath",
    );
    expect(() =>
      gate.expectError({
        text: "a",
        urlPath: "/x",
        status: 404,
        count: 1,
      } as never),
    ).toThrow("CONSOLE_GATE: expectError takes text or urlPath, not both");
    expect(() => gate.expectError({ text: "a", count: 0 })).toThrow(
      "CONSOLE_GATE: expectError count must be an integer >= 1, got 0",
    );
    expect(() => gate.expectError({ text: "a", count: -1 })).toThrow(
      "CONSOLE_GATE: expectError count must be an integer >= 1, got -1",
    );
    expect(() => gate.expectError({ text: "a", count: 1.5 })).toThrow(
      "CONSOLE_GATE: expectError count must be an integer >= 1, got 1.5",
    );
    expect(() =>
      gate.expectError({ urlPath: "/x", status: 399, count: 1 }),
    ).toThrow("CONSOLE_GATE: expectError status must be 400-599, got 399");
    expect(() =>
      gate.expectError({ urlPath: "/x", status: 600, count: 1 }),
    ).toThrow("CONSOLE_GATE: expectError status must be 400-599, got 600");
    gate.expectError({ text: "DUP", count: 1 });
    expect(() => gate.expectError({ text: "DUP", count: 1 })).toThrow(
      'CONSOLE_GATE: duplicate expectError "DUP"',
    );
    // Drain the leftover expectation so fixture teardown stays clean.
    expect(() => gate.assertClean()).toThrow(
      'CONSOLE_GATE: expected error "DUP" x1, got 0',
    );
  });

  test("E10 attachConsoleGate throws without fixtures gate", async ({
    browser,
  }) => {
    const page = await browser.newPage();
    try {
      expect(() => attachConsoleGate(page)).toThrow(
        "CONSOLE_GATE: no strict gate attached to this page",
      );
    } finally {
      await page.close();
    }
  });

  test("E11 gate catches errors on first document load", async ({
    page,
    gate,
  }) => {
    await page.route("**/__e2e_gate/early", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/html",
        body: '<!doctype html><html><body><script>console.error("EARLY")</script></body></html>',
      });
    });
    await page.goto("/__e2e_gate/early");
    await expect(async () => gate.assertClean()).rejects.toThrow(
      "CONSOLE_GATE: expected 0 app errors, got 1: EARLY",
    );
  });

  test("G7 fixture teardown asserts when body skips assertClean", async ({
    page,
  }) => {
    test.fail();
    await page.goto("about:blank");
    await page.evaluate(() => console.error("TEARDOWN_MUST_CATCH"));
    // Intentionally no assertClean — auto fixture teardown must fail the test.
  });
});

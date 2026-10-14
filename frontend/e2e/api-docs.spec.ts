import { expect, test } from "@playwright/test";

const MINIMAL_OPENAPI = {
  openapi: "3.0.3",
  info: {
    title: "Scot-LAND API",
    version: "0.0.0-e2e",
    description: "Fixture schema for Playwright — not live market rents.",
  },
  paths: {
    "/health": {
      get: {
        operationId: "health_check",
        summary: "Health",
        responses: {
          "200": {
            description: "ok",
          },
        },
      },
    },
    "/api/catalog.json": {
      get: {
        operationId: "catalog",
        summary: "Catalog",
        responses: {
          "200": {
            description: "ok",
          },
        },
      },
    },
  },
};

test.describe("API reference (charter C1)", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("/developers/api renders Swagger opblocks without CDN CSP errors", async ({
    page,
  }) => {
    const cspViolations: string[] = [];
    page.on("console", (msg) => {
      const text = msg.text();
      if (/Content Security Policy|csp|jsdelivr/i.test(text)) {
        cspViolations.push(text);
      }
    });

    await page.route("**/backend/openapi.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MINIMAL_OPENAPI),
      });
    });

    const bundleOk = page.waitForResponse(
      (r) => r.url().includes("/swagger-ui/swagger-ui-bundle.js") && r.ok(),
    );
    const cssOk = page.waitForResponse(
      (r) => r.url().includes("/swagger-ui/swagger-ui.css") && r.ok(),
    );
    await page.goto("/developers/api");
    await Promise.all([bundleOk, cssOk]);

    await expect(page.getByTestId("api-reference-page")).toBeVisible();
    await expect(page.locator(".swagger-ui .opblock").first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.locator(".swagger-ui .opblock")).toHaveCount(2);
    expect(cspViolations).toEqual([]);
  });

  test("/docs and /backend/docs 301 to /developers/api", async ({
    request,
  }) => {
    for (const path of ["/docs", "/backend/docs"]) {
      const res = await request.fetch(path, { maxRedirects: 0 });
      expect(
        [301, 308].includes(res.status()),
        `${path} status ${res.status()}`,
      ).toBeTruthy();
      const location = res.headers().location || "";
      expect(location).toMatch(/\/developers\/api$/);
    }

    const followed = await request.get("/docs");
    expect(followed.status()).toBe(200);
    expect(followed.url()).toMatch(/\/developers\/api\/?$/);
  });
});

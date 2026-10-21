import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test } from "./_fixtures";

registerOpenFreeMapFontStub();


test.describe("API reference (charter C1)", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("/developers/api teaser does not load Swagger or a CDN", async ({
    page,
  }) => {
    const cspViolations: string[] = [];
    const validatorHits: string[] = [];
    page.on("console", (msg) => {
      const text = msg.text();
      if (/Content Security Policy|csp|jsdelivr|validator\.swagger\.io/i.test(text)) {
        cspViolations.push(text);
      }
    });
    page.on("request", (req) => {
      const url = req.url();
      if (
        /validator\.swagger\.io|jsdelivr|\/swagger-ui\/swagger-ui-bundle\.js|\/swagger-ui\/swagger-ui\.css/i.test(
          url,
        )
      ) {
        validatorHits.push(url);
      }
    });

    await page.goto("/developers/api");
    await expect(page.getByTestId("api-teaser")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Developer API and bulk data: later",
    );
    await expect(page.locator(".swagger-ui")).toHaveCount(0);
    await expect(page.locator(".swagger-ui .opblock")).toHaveCount(0);
    expect(cspViolations).toEqual([]);
    expect(validatorHits).toEqual([]);
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

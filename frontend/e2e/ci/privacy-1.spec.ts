import { expect, test, type Page } from "@playwright/test";

/**
 * PRIVACY-1 — contact form states, and a crawl of the sitemap.
 * HTML and first-party JS must not carry GitHub, a name, or an email,
 * except the single allowed phrase on /how-we-built-this.
 */

const EMAIL_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i;
const ALLOWED = "led by Laurie Moffat";
const FORM_ID = "pwpublic";

function nameHits(text: string, allowPhrase: boolean): string[] {
  const source = allowPhrase ? text.split(ALLOWED).join("") : text;
  return source.match(/Laurie|Moffat/g) ?? [];
}

async function firstPartyJs(page: Page): Promise<string> {
  const srcs = await page.locator("script[src]").evaluateAll((els) =>
    els
      .map((el) => el.getAttribute("src") ?? "")
      .filter((src) => src.length > 0 && !/swagger-ui/i.test(src)),
  );
  const chunks: string[] = [];
  for (const src of srcs) {
    const url = new URL(src, page.url());
    if (url.origin !== new URL(page.url()).origin) continue;
    const response = await page.request.get(url.pathname + url.search);
    if (response.ok()) chunks.push(await response.text());
  }
  return chunks.join("\n");
}

test.describe("PRIVACY-1 contact form", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("unset id shows coming soon and no address", async ({ page }) => {
    await page.goto("/about#contact");
    await expect(page.getByTestId("contact-form-soon")).toHaveText(
      "Contact form coming soon",
    );
    await expect(page.getByTestId("contact-form")).toHaveCount(0);
    const html = await page.locator("#contact").innerHTML();
    expect(html).not.toMatch(EMAIL_RE);
    expect(html).not.toMatch(/mailto:/i);
  });

  test("flag off stays coming soon even if an id is injected", async ({ page }) => {
    const posts: string[] = [];
    await page.addInitScript((id) => {
      (window as Window & { __SC_CONTACT_FORM_ID?: string }).__SC_CONTACT_FORM_ID =
        id;
    }, FORM_ID);
    await page.route("**/formspree.io/f/**", async (route) => {
      posts.push(route.request().postData() ?? "");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
    });
    await page.goto("/about#contact");
    await expect(page.getByTestId("contact-form-soon")).toHaveText(
      "Contact form coming soon",
    );
    await expect(page.getByTestId("contact-form")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Send" })).toHaveCount(0);
    expect(posts).toEqual([]);
    const html = await page.locator("#contact").innerHTML();
    expect(html).not.toMatch(EMAIL_RE);
    expect(html).not.toMatch(/mailto:/i);
  });
});

test.describe("PRIVACY-1 crawl", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("sitemap pages have no github, name, or email", async ({ page }) => {
    test.setTimeout(180_000);
    const sitemap = await page.request.get("/sitemap.xml");
    expect(sitemap.ok()).toBe(true);
    const xml = await sitemap.text();
    const locs = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => {
      const url = new URL(match[1]!);
      return url.pathname;
    });
    expect(locs.length).toBeGreaterThan(5);
    const paths = [...new Set([...locs, "/about"])];

    for (const path of paths) {
      await page.goto(path === "/about" ? "/about#contact" : path);
      const html = await page.content();
      const js = await firstPartyJs(page);
      const allow = path === "/how-we-built-this";
      for (const [kind, text] of [
        ["html", html],
        ["js", js],
      ] as const) {
        expect(text, `${path} ${kind} github`).not.toMatch(/github/i);
        expect(nameHits(text, allow), `${path} ${kind} name`).toEqual([]);
        expect(text, `${path} ${kind} email`).not.toMatch(EMAIL_RE);
      }
      if (allow) {
        const visible = await page.getByTestId("how-we-built-copy").innerText();
        expect(visible.match(/led by Laurie Moffat/g)).toEqual([
          "led by Laurie Moffat",
        ]);
      }
    }

    await page.goto("/roadmap");
    await expect(page.getByRole("link", { name: "Suggest a layer" })).toHaveAttribute(
      "href",
      "/about#contact",
    );
    await page.goto("/developers/api");
    await expect(page.getByRole("link", { name: "Register interest" })).toHaveAttribute(
      "href",
      "/about#contact",
    );
    await page.goto("/how-we-built-this");
    await expect(page.getByRole("link", { name: "get in touch" })).toHaveAttribute(
      "href",
      "/about#contact",
    );
  });
});

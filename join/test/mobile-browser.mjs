// Local-only review fixture. Never send test drafts to the public desk.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { chromium } from "@playwright/test";
const root = new URL("../dist/", import.meta.url);
const catalog = JSON.parse(
  await readFile(new URL("../src/tasks.json", import.meta.url)),
);
const server = createServer(async (req, res) => {
  const path = new URL(req.url, "http://localhost").pathname;
  if (!/^\/(?:assets\/[\w.-]+|index\.html)?$/.test(path)) {
    res.writeHead(404).end();
    return;
  }
  const file = path === "/" ? "index.html" : path.slice(1);
  res.setHeader(
    "content-type",
    file.endsWith(".js")
      ? "text/javascript"
      : file.endsWith(".css")
        ? "text/css"
        : "text/html",
  );
  res.end(await readFile(new URL(file, root)));
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const browser = await chromium.launch({ channel: "chrome" });
try {
  for (const width of [390, 1280]) {
    const context = await browser.newContext({
      viewport: { width, height: 840 },
    });
    const page = await context.newPage();
    const mine = [];
    let submissions = 0,
      connected = true;
    await page.route("**/api/*", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (!connected) return route.abort();
      if (path.endsWith("/claim") && !mine.length)
        mine.push({
          id: catalog[0].id,
          user: "tester",
          state: "held",
          claimed: Date.now(),
          draft: "",
        });
      if (path.endsWith("/submit")) {
        Object.assign(mine[0], {
          state: "pending",
          draft: route.request().postDataJSON().draft,
        });
        submissions++;
      }
      await route.fulfill({
        json: path.endsWith("/desk")
          ? {
              tasks: catalog.map((t) => ({
                ...t,
                available: !mine.some((m) => m.id === t.id),
              })),
              user: "tester",
              loginReady: true,
              reviewer: false,
              mine,
              queue: [],
            }
          : mine[0],
      });
    });
    await page.goto("http://127.0.0.1:" + server.address().port);
    await page.getByRole("button", { name: "tester · Выйти" }).waitFor();
    await page.locator("#reserve").click();
    await page
      .getByText("Задача закреплена. Можно продолжить без сети.")
      .waitFor();
    await page.locator("#draft").fill("Translated text.");
    connected = false;
    await page.locator("#send").click();
    await page.getByText(/Черновик сохранен/).waitFor();
    connected = true;
    await page.evaluate(() => window.dispatchEvent(new Event("online")));
    await page.getByText(/^Квитанция join-pl/).waitFor();
    assert.equal(submissions, 1);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await context.close();
    console.log(width + "px: reserved, queued offline, received once.");
  }
} finally {
  await browser.close();
  server.close();
}

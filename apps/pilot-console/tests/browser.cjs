const { chromium } = require("playwright");
const assert = require("node:assert/strict");
(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
    args: [
      "--no-sandbox",
      ...(process.env.CHROMIUM_EXECUTABLE_PATH
        ? ["--single-process", "--no-zygote", "--disable-gpu"]
        : []),
    ],
  });
  console.log("Browser launched");
  const page = await browser.newPage({
    viewport: { width: 1512, height: 1100 },
    reducedMotion: "reduce",
  });
  await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("http://127.0.0.1:3000");
  console.log("Page loaded");
  await page.waitForSelector(".zone");
  await page.screenshot({ path: "/tmp/tectonic-overview.png", fullPage: true });
  console.log("Screenshot saved");
  await page.locator(".zone").first().click();
  await page.waitForURL("**/#/workspace/experience");
  await page.locator('a[href="#/agents/experience-0"]').click();
  await page.waitForSelector("h1");
  await page.goto("http://127.0.0.1:3000/#/capabilities");
  await page.locator("#catalog-search").fill("llm");
  assert((await page.locator("#catalog-results .module-card").count()) > 0);
  await page.goto("http://127.0.0.1:3000/#/capabilities/llm-gateway/api");
  await page.locator("[data-endpoint]").first().click();
  await page.locator("dialog[open]").waitFor();
  await page.keyboard.press("Escape");
  for (const scenario of ["policy", "order", "refund"]) {
    console.log("Checking scenario:", scenario);
    await page.goto("http://127.0.0.1:3000/#/overview");
    await page.locator(`[data-scenario="${scenario}"]`).click();
    if (scenario === "refund") {
      await page
        .getByRole("button", { name: "Open human review →" })
        .waitFor({ timeout: 15000 });
      await page.getByRole("button", { name: "Open human review →" }).click();
      await page.getByRole("button", { name: "Claim request" }).click();
      await page
        .locator("textarea[name=reason]")
        .fill("Reviewed against the demonstration policy.");
      await page.getByRole("button", { name: "Approve & resume" }).click();
    }
    await page
      .locator(".run-top .badge")
      .filter({ hasText: /^completed$/ })
      .waitFor({ timeout: 15000 });
    if (scenario === "policy") {
      await page.locator("[data-document]").click();
      assert((await page.locator("dialog").innerText()).includes("30 days"));
      await page.keyboard.press("Escape");
    }
    await page.locator(".run-step").nth(2).click();
    await page.locator("pre").waitFor();
  }
  await page.goto("http://127.0.0.1:3000/#/runs");
  assert.equal(await page.locator("tbody tr").count(), 3);
  await page.reload();
  assert.equal(await page.locator("tbody tr").count(), 3);
  await page.locator("#tenant-button").click();
  await page.locator('[data-tenant="Globex"]').click();
  await page.goto("http://127.0.0.1:3000/#/runs");
  assert.equal(await page.locator("tbody tr").count(), 0);
  await page.locator("#tenant-button").click();
  await page.locator('[data-tenant="Acme"]').click();
  await page.locator('header [data-action="lead"]').click();
  for (const [key, value] of Object.entries({
    name: "QA Visitor",
    email: "qa@example.com",
    company: "Demo QA",
    goal: "Assess a governed customer support pilot.",
  }))
    await page.locator(`#lead-form [name=${key}]`).fill(value);
  await page.locator("#lead-form [name=consent]").check();
  await page.locator("#lead-form button[type=submit]").click();
  await page
    .getByRole("heading", { name: "Your pilot brief is captured." })
    .waitFor();
  await page.keyboard.press("Escape");
  for (const route of [
    "overview",
    "workspace",
    "runs",
    "reviews",
    "knowledge",
    "agents",
    "assurance",
    "capabilities",
  ]) {
    await page.goto("http://127.0.0.1:3000/#/" + route);
    await page.locator("h1").waitFor();
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
      "overflow " + route,
    );
  }
  await page.goto("http://127.0.0.1:3000/#/overview");
  await page.screenshot({
    path: "/tmp/tectonic-overview-active.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of [
    "overview",
    "workspace",
    "runs",
    "reviews",
    "knowledge",
    "agents",
    "assurance",
    "capabilities",
  ]) {
    await page.goto("http://127.0.0.1:3000/#/" + route);
    await page.locator("h1").waitFor();
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
      "mobile overflow " + route,
    );
  }
  await page.goto("http://127.0.0.1:3000/#/overview");
  await page.screenshot({ path: "/tmp/tectonic-mobile.png", fullPage: true });
  assert.deepEqual(errors, []);
  console.log(
    "PASS: navigation, 3 journeys, review/resume, evidence, persistence, tenant demo, lead capture, 8 desktop/mobile routes; no JS errors",
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

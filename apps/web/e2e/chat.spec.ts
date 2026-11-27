import { expect, test } from "@playwright/test";

/**
 * Main chat flow against the real API and the seeded data (seed/lgu). Asserted facts come
 * from the seed files only (rule 1).
 */

test.beforeEach(async ({ page }) => {
  // A fresh chat per test; a test that reloads sets sessionStorage "keep" first.
  await page.addInitScript(() => {
    if (!window.sessionStorage.getItem("keep")) window.localStorage.clear();
  });
});

test("welcome page leads to the chat with starter questions", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Start chat" }).click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByText("Online")).toBeVisible();
  await expect(page.getByRole("list", { name: "Starter questions" })).toBeVisible();
  await expect(page.getByText(/Please confirm important decisions/)).toBeVisible();
});

test("a fee question streams an exact answer with its source and badge", async ({ page }) => {
  await page.goto("/chat");
  await expect(page.getByText("Online")).toBeVisible();
  await page.getByRole("button", { name: "What are the fees for BSCS?" }).click();
  await expect(page.getByText(/Rs 7,744 per credit hour/)).toBeVisible();
  await expect(page.getByText("Last verified 5 Oct 2026")).toBeVisible();
  const chip = page.getByRole("button", { name: /Fee Structure page/ });
  await chip.click();
  await expect(page.getByRole("dialog", { name: "Source" })).toContainText("5 Oct 2026");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("a question with no verified data shows the fallback card", async ({ page }) => {
  await page.goto("/chat");
  await expect(page.getByText("Online")).toBeVisible();
  const box = page.getByLabel("Type a message");
  await box.fill("Is there a swimming pool on campus?");
  await box.press("Enter");
  await expect(page.getByText("I don't have verified information on this.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Call 0322-2757543" })).toHaveAttribute(
    "href",
    "tel:03222757543",
  );
});

test("the conversation survives a reload and accepts feedback", async ({ page }) => {
  await page.goto("/chat");
  await expect(page.getByText("Online")).toBeVisible();
  const box = page.getByLabel("Type a message");
  await box.fill("Exam office phone number?");
  await box.press("Enter");
  await expect(page.getByRole("link", { name: "042-37181828" })).toBeVisible();
  await page.getByRole("button", { name: "Helpful", exact: true }).click();
  await expect(page.getByText("Thanks for the feedback")).toBeVisible();

  // Reload without clearing storage: history comes back over REST.
  await page.evaluate(() => {
    window.sessionStorage.setItem("keep", "1");
  });
  await page.goto("/chat", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Exam office phone number?")).toBeVisible();
  await expect(page.getByRole("link", { name: "042-37181828" })).toBeVisible();
});

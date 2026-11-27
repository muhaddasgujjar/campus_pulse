import { expect, test } from "@playwright/test";

import { installVoiceFakes } from "./voiceFakes";

/**
 * Voice end to end (M4) against the real API and seed data, with fake speech engines (see
 * voiceFakes.ts). Real devices and real Urdu speech are covered by the manual test sheet.
 */

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.clear());
});

test("a voice message is transcribed live, answered and can be listened to", async ({ page }) => {
  await installVoiceFakes(page, { recognition: true });
  await page.goto("/chat");
  await expect(page.getByText("Online")).toBeVisible();
  await page.getByRole("button", { name: "Record a voice message" }).click();
  await expect(page.getByRole("button", { name: "Send voice message" })).toBeEnabled();
  await page.evaluate(() => (window as unknown as { __say: (t: string) => void }).__say("Exam office phone number?"));
  await expect(page.getByText("Exam office phone number?")).toBeVisible();
  await page.getByRole("button", { name: "Send voice message" }).click();
  await expect(page.getByText(/^Voice message · 0:0\d$/)).toBeVisible();
  await expect(page.getByRole("link", { name: "042-37181828" })).toBeVisible();
  await page.getByRole("button", { name: "Listen" }).click();
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.join(" ")))
    .toContain("Exam Office: phone 042-37181828");
});

test("without browser recognition the recording is transcribed by the server", async ({ page }) => {
  await installVoiceFakes(page, { recognition: false });
  await page.goto("/chat");
  await expect(page.getByText("Online")).toBeVisible();
  await page.getByRole("button", { name: "Record a voice message" }).click();
  await expect(page.getByText("Recording… the transcript appears after sending.")).toBeVisible();
  await page.waitForTimeout(800); // record a little real audio
  const upload = page.waitForResponse((r) => r.url().includes("/api/voice/transcribe"));
  await page.getByRole("button", { name: "Send voice message" }).click();
  expect((await upload).status()).toBe(200);
  // STT_MODEL=fake on the e2e API answers with a fixed transcript
  await expect(page.getByText("What are the fees for BSCS?")).toBeVisible();
  await expect(page.getByText(/Rs 7,744 per credit hour/)).toBeVisible();
});

test("live mode answers out loud and returns to the chat", async ({ page }) => {
  await installVoiceFakes(page, { recognition: true });
  await page.goto("/chat");
  await expect(page.getByText("Online")).toBeVisible();
  await page.getByRole("button", { name: "Live mode" }).click();
  await expect(page.getByRole("dialog", { name: "Live mode" })).toBeVisible();
  await expect(page.getByText("Listening…")).toBeVisible();
  await page.evaluate(() => (window as unknown as { __say: (t: string) => void }).__say("Exam office phone number?"));
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.join(" ")))
    .toContain("Exam Office: phone 042-37181828");
  await page.getByRole("button", { name: "End live mode" }).click();
  await expect(page.getByRole("dialog", { name: "Live mode" })).toBeHidden();
  await expect(page.getByText("Exam office phone number?")).toBeVisible();
});

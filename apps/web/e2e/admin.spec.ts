import { expect, type Page, test } from "@playwright/test";

/**
 * Admin portal against the real local API (DEV_AUTH: admin@local.test and staff@local.test,
 * created by app.devtools.serve). Covers the M5 exit criterion: staff write an entry, an admin
 * approves it, and the chat answers from it.
 */

async function signIn(page: Page, email: string) {
  await page.goto("/admin");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/admin\/dashboard$/);
}

async function signOutOf(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Staff sign in" })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!window.sessionStorage.getItem("keep")) window.localStorage.clear();
    window.sessionStorage.setItem("keep", "1"); // keep the sign-in across page loads in a test
  });
});

test("the portal needs a sign-in", async ({ page }) => {
  await page.goto("/admin/users");
  await expect(page.getByRole("heading", { name: "Staff sign in" })).toBeVisible();
});

test("staff without a department are not offered the timetable import", async ({ page }) => {
  await signIn(page, "staff@local.test"); // Admission Office, no department
  await page.goto("/admin/content?tab=timetable");
  await expect(page.getByRole("button", { name: /Add class/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Import CSV" })).toHaveCount(0);
});

test("staff see only their screens; admins see everything", async ({ page }) => {
  await signIn(page, "staff@local.test");
  const nav = page.getByRole("navigation", { name: "Admin" });
  await expect(nav.getByRole("link", { name: "Content" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Users" })).toHaveCount(0);
  await expect(page.getByText("Staff · Admission Office")).toBeVisible();
  await signOutOf(page);

  await signIn(page, "admin@local.test");
  await expect(nav.getByRole("link", { name: "Users" })).toBeVisible();
  await expect(page.getByText("Questions today")).toBeVisible();
});

test("staff entry, approved by an admin, is answered by the chat", async ({ page }) => {
  const stamp = Date.now().toString(36);
  const title = `Evening shuttle to Gulberg ${stamp}`;

  await signIn(page, "staff@local.test");
  await page.goto("/admin/content/kb/new");
  await page.getByLabel(/^Title/).fill(title);
  await page.getByLabel("Question students ask").fill("Is there an evening shuttle to Gulberg?");
  await page.getByLabel(/^Answer/).fill("The evening shuttle to Gulberg leaves the main gate at 17:30 on weekdays.");
  await page.getByLabel(/^Category/).selectOption("transport");
  await expect(page.getByRole("complementary", { name: "Preview" })).toContainText("17:30");
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByText("Pending", { exact: true })).toBeVisible();
  await signOutOf(page);

  await signIn(page, "admin@local.test");
  await page.getByRole("link", { name: "Approvals" }).click();
  const card = page.locator("section", { hasText: title });
  await expect(card).toContainText("new");
  await card.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText(/approved and live in the chat/)).toBeVisible();

  await page.getByRole("link", { name: "Audit" }).click();
  await expect(page.getByRole("cell", { name: "staff:staff@local.test" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "admin:admin@local.test" }).first()).toBeVisible();

  await page.goto("/chat");
  await expect(page.getByText("Online")).toBeVisible();
  await page.getByLabel("Type a message").fill("Is there an evening shuttle to Gulberg?");
  await page.keyboard.press("Enter");
  await expect(page.getByText(/17:30/).last()).toBeVisible();
});

test("a CSV with a bad row is refused with the row's error", async ({ page }) => {
  await signIn(page, "admin@local.test");
  await page.goto("/admin/content?tab=timetable");
  await page.getByRole("button", { name: "Import CSV" }).click();
  const csv =
    "program,semester,section,day,start_time,end_time,course_code,course_name,faculty_name,room,effective_from,effective_to,last_verified,source_name\n" +
    "BSCS,13,A,Mon,09:00,10:00,CS-201,Data Structures,,C-12,,,2026-11-01,Test\n";
  await page.locator('input[type="file"]').setInputFiles({ name: "bad.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Nothing was imported");
  await expect(page.getByRole("dialog").getByRole("button", { name: /rows$/ })).toBeDisabled();
});

test("a student saves a profile and deletes their data", async ({ page }) => {
  await page.goto("/chat");
  await expect(page.getByText("Online")).toBeVisible();
  await page.getByRole("button", { name: "Your profile" }).click();
  await page.getByLabel("Program").fill("BSCS");
  await page.getByLabel("Semester").selectOption("3");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/Saved\./)).toBeVisible();
  await page.getByRole("button", { name: "Delete my data" }).click();
  await page.getByRole("button", { name: "Delete my data" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
});

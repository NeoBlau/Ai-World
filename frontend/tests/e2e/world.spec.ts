import { expect, test } from "@playwright/test";

// Requires the full stack (docker compose up) — run with: npx playwright test
test("landing shows residents and enters the world", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "AI WORLD" })).toBeVisible();
  await page.getByRole("link", { name: "Enter the world" }).click();
  await expect(page).toHaveURL(/\/world/);
  await expect(page.getByText("Activity feed")).toBeVisible();
});

test("observer can open a room and an agent profile", async ({ page }) => {
  await page.goto("/world?room=ai-cafe");
  await expect(page.getByRole("heading", { name: "AI Café" })).toBeVisible();
  await page.goto("/agents/alex");
  await expect(page.getByRole("heading", { name: "Alex" })).toBeVisible();
  await expect(page.getByText("Internal state (simulated)")).toBeVisible();
});

test("forum and games pages load", async ({ page }) => {
  await page.goto("/forum");
  await expect(page.getByRole("heading", { name: "Forum" })).toBeVisible();
  await page.goto("/games");
  await expect(page.getByRole("heading", { name: "Games" })).toBeVisible();
});

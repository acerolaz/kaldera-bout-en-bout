import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("page d'attente du back-office", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { level: 1, name: "Kaldera · back-office gestionnaire" }),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
});

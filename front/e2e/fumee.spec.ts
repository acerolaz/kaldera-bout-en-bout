import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const sansViolation = async (page: Page) =>
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
const theme = (page: Page) => page.evaluate(() => document.documentElement.dataset.theme);

test("E1, thème mémorisé sans flash, axe dans les deux thèmes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Liste des demandes" })).toBeVisible();
  expect(await theme(page)).toBe("light");
  await sansViolation(page);

  await page.getByRole("button", { name: "Passer au thème sombre" }).click();
  expect(await theme(page)).toBe("dark");
  await sansViolation(page);

  await page.reload({ waitUntil: "domcontentloaded" });
  expect(await theme(page)).toBe("dark"); // posé par le script de index.html, avant React
  await expect(page.getByRole("button", { name: "Passer au thème clair" })).toBeVisible();
});

test("sans choix enregistré, le thème suit le système", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  expect(await theme(page)).toBe("dark");
});

test("clavier : lien d'évitement, Demandes, bouton de thème", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Aller au contenu" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Demandes" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: /Passer au thème/ })).toBeFocused();
});

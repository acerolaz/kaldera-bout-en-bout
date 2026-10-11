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

  // Bundle bloqué : seul le script inline de index.html peut poser le thème (avant React).
  await page.route("**/src/main.tsx", (r) => r.abort());
  await page.reload({ waitUntil: "domcontentloaded" });
  expect(await theme(page)).toBe("dark");
  await page.unroute("**/src/main.tsx");
  await page.reload();
  await expect(page.getByRole("button", { name: "Passer au thème clair" })).toBeVisible();
});

test("sans choix enregistré, le thème suit le système", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.route("**/src/main.tsx", (r) => r.abort()); // seul le script inline agit
  await page.goto("/");
  expect(await theme(page)).toBe("dark");
});

test("clavier : lien d'évitement, Demandes, bouton de thème (anneau or clair)", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await page.keyboard.press("Tab");
  const evitement = page.getByRole("link", { name: "Aller au contenu" });
  await expect(evitement).toBeFocused();
  await expect(evitement).toHaveCSS("outline-color", "rgb(250, 204, 21)"); // #FACC15
  await page.keyboard.press("Tab");
  const demandes = page.getByRole("link", { name: "Demandes" });
  await expect(demandes).toBeFocused();
  await expect(demandes).toHaveCSS("outline-color", "rgb(250, 204, 21)");
  await page.keyboard.press("Tab");
  const bouton = page.getByRole("button", { name: /Passer au thème/ });
  await expect(bouton).toBeFocused();
  await expect(bouton).toHaveCSS("box-shadow", /rgb\(250, 204, 21\)/);
});

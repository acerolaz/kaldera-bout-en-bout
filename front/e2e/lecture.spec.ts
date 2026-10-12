import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const sansViolation = async (page: Page) =>
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);

test("E1 liste et filtre ; E2 timeline, anti-fraude et garanties ; axe dans les deux thèmes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(page.getByRole("link", { name: "KAL-26-0103" })).toBeVisible();
  await expect(page.getByRole("link", { name: "KAL-26-0203" })).toBeVisible();
  await expect(page.getByRole("link", { name: "KAL-26-0101" })).toBeVisible();
  await sansViolation(page);

  await page.getByLabel("Issue").selectOption("escalade");
  await expect(page).toHaveURL(/\?issue=escalade$/);
  await expect(page.getByRole("link", { name: "KAL-26-0203" })).toBeVisible();
  await expect(page.getByRole("link", { name: "KAL-26-0103" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByLabel("Issue")).toHaveValue("escalade");

  await page.getByRole("link", { name: "KAL-26-0203" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Dossier KAL-26-0203" })).toBeVisible();
  const timeline = page.getByRole("list", { name: "Étapes du traitement" });
  await expect(timeline.getByRole("listitem")).toHaveCount(5);
  await expect(page.getByRole("region", { name: "Carte anti-fraude" })).toBeVisible();
  await sansViolation(page);

  await page.getByRole("button", { name: "Garanties" }).click();
  await expect(page.getByRole("dialog", { name: "Garanties" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByRole("button", { name: "Passer au thème sombre" }).click();
  await sansViolation(page);
  await page.goto("/");
  await sansViolation(page);
});

test("référence inconnue : Dossier introuvable", async ({ page }) => {
  await page.goto("/demandes/KAL-26-9999");
  await expect(page.getByText("Dossier introuvable.")).toBeVisible();
  await page.getByRole("link", { name: "Retour à la liste des demandes" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Liste des demandes" })).toBeVisible();
});

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const sansViolation = async (page: Page) =>
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);

// base partagée par les deux projets : chacun lance ses propres dossiers prêts
const JEUX: Record<string, [string, string[]]> = {
  mobile: ["KAL-26-0104", ["KAL-26-0105", "KAL-26-0106", "KAL-26-0107"]],
  desktop: ["KAL-26-0108", ["KAL-26-0109", "KAL-26-0110", "KAL-26-0111"]],
};

test("traiter 1 dossier (E2 en direct) puis un lot (E3) ; axe dans les deux thèmes", async ({ page }, info) => {
  const [seul, lot] = JEUX[info.project.name];
  await page.emulateMedia({ colorScheme: "light" });

  await page.goto("/?statut=prete");
  await expect(page.getByRole("checkbox", { name: "Sélectionner KAL-26-0101" })).toHaveCount(0); // filtre prete
  await page.getByRole("checkbox", { name: `Sélectionner ${seul}` }).check();
  await page.getByRole("button", { name: "Traiter la sélection (1)" }).click();
  await expect(page).toHaveURL(new RegExp(`/demandes/${seul}$`));
  await expect(page.getByRole("progressbar", { name: "Avancement du dossier" })).toHaveAttribute("aria-valuenow", "100", {
    timeout: 15_000,
  });
  await expect(page.getByText("Traitement terminé")).toBeVisible();
  await sansViolation(page);

  await page.goto("/?statut=prete");
  for (const reference of lot) await page.getByRole("checkbox", { name: `Sélectionner ${reference}` }).check();
  await page.getByRole("button", { name: "Traiter la sélection (3)" }).click();
  await expect(page).toHaveURL(/\/lots\/\d+$/);
  await expect(page.getByRole("progressbar", { name: "Avancement du lot" })).toHaveAttribute("aria-valuenow", "100", {
    timeout: 20_000,
  });
  for (const reference of lot) {
    await expect(page.getByRole("progressbar", { name: `Avancement de ${reference}` })).toHaveAttribute("aria-valuenow", "100");
  }
  await sansViolation(page);
  await page.getByRole("button", { name: "Passer au thème sombre" }).click();
  await sansViolation(page);

  await page.getByRole("link", { name: lot[0] }).click();
  await expect(page.getByRole("heading", { level: 1, name: `Dossier ${lot[0]}` })).toBeVisible();

  await page.goto("/");
  await expect(page.getByRole("checkbox", { name: `Sélectionner ${seul}` })).toBeDisabled(); // déjà traité
});

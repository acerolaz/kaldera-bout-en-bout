import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const MOT_DE_PASSE = process.env.KALDERA_DEMO_MOT_DE_PASSE ?? "kaldera-demo";
const INTERDITS = /fraude|partenaire|repli|score|cellule|d[ée]grad|trace|indicateur|antifraude/i;
// axe lit les couleurs calculées : on attend la fin des animations (ouverture du Sheet) pour ne pas mesurer un fondu.
const sansViolation = async (page: Page) => {
  await page.waitForFunction(() => document.getAnimations().length === 0);
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
};

const PIECES = path.resolve(process.cwd(), "../fixtures/pieces"); // cwd = front/ (ESM : pas de __dirname)

test("parcours de l'assuré : dépôt, relance, soumission, verdict", async ({ page }, info) => {
  test.skip(info.project.name === "desktop", "une seule base : le parcours complet tourne une fois (mobile)");
  await page.goto("/connexion");
  await page.getByLabel("Identifiant").fill("claire");
  await page.getByLabel("Mot de passe").fill(MOT_DE_PASSE);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.getByRole("link", { name: /Sinistre KAL-26-0101/ }).click();
  await expect(page.getByText("En attente de vos pièces").first()).toBeVisible();
  await sansViolation(page);

  // facture illisible → message spontané de l'assistant
  await page.getByLabel("Type de pièce").selectOption("facture");
  await page.getByLabel("Choisir un fichier").setInputFiles(path.join(PIECES, "KAL-26-0601/initiale_01_facture.pdf"));
  await page.getByRole("button", { name: "Envoyer la pièce" }).click();
  await expect(page.getByText("À refaire")).toBeVisible({ timeout: 30_000 });
  await sansViolation(page);

  await page.getByRole("button", { name: /Aide sur mes pièces/ }).click();
  await expect(page.getByRole("log")).toContainText("n'a pas pu être lu");
  await sansViolation(page); // chat ouvert
  await page.getByLabel("Votre message").fill("Pourquoi ma facture est refusée ?");
  await page.getByRole("button", { name: "Envoyer" }).click();
  await expect(page.getByRole("log").locator("li").filter({ hasText: "n'a pas pu être lu" })).toHaveCount(2, { timeout: 15_000 });
  await expect(page.getByRole("log")).not.toContainText(INTERDITS);
  await page.getByRole("button", { name: "Déposer maintenant" }).first().click();
  // le focus va à la zone de dépôt (et non au bouton du chat)
  await expect(page.getByLabel("Type de pièce")).toBeFocused();

  // bonnes pièces
  await page.getByLabel("Type de pièce").selectOption("facture");
  await page.getByLabel("Choisir un fichier").setInputFiles(path.join(PIECES, "KAL-26-0101/initiale_01_facture.pdf"));
  await page.getByRole("button", { name: "Envoyer la pièce" }).click();
  // attendre l'accusé : choisir un fichier pendant l'envoi serait effacé par la fin du premier dépôt
  await expect(page.getByText("Pièce reçue, analyse en cours.")).toBeVisible();
  await page.getByLabel("Type de pièce").selectOption("photo");
  await page.getByLabel("Choisir un fichier").setInputFiles(path.join(PIECES, "KAL-26-0101/initiale_02_photo.png"));
  await page.getByRole("button", { name: "Envoyer la pièce" }).click();
  await expect(page.getByText("Validée")).toHaveCount(2, { timeout: 30_000 });

  await page.getByRole("button", { name: "Soumettre mon dossier" }).click();
  await expect(page.getByRole("heading", { name: "Décision" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Remboursement accordé")).toBeVisible();
  await expect(page.getByText(/1[\s  ]700,00[\s  ]€/).first()).toBeVisible();
  await sansViolation(page);
  await expect(page.locator("body")).not.toContainText(INTERDITS);
});

test("la page de connexion est accessible (desktop et mobile)", async ({ page }) => {
  await page.goto("/connexion");
  await sansViolation(page);
});

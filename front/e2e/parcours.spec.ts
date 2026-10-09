import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import path from "node:path";

const PIECES = path.resolve(process.cwd(), "../fixtures/pieces"); // cwd = front/ (ESM : pas de __dirname)

test("parcours de l'assuré : dépôt, relance, soumission, verdict", async ({ page }, info) => {
  test.skip(info.project.name === "desktop", "une seule base : le parcours complet tourne une fois (mobile)");
  await page.goto("/connexion");
  await page.getByLabel("Identifiant").fill("claire");
  await page.getByLabel("Mot de passe").fill("kaldera-demo");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.getByRole("link", { name: /Sinistre KAL-26-0101/ }).click();
  await expect(page.getByText("En attente de vos pièces").first()).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);

  // facture illisible → message spontané de l'assistant
  await page.getByLabel("Type de pièce").selectOption("facture");
  await page.getByLabel("Choisir un fichier").setInputFiles(path.join(PIECES, "KAL-26-0601/initiale_01_facture.pdf"));
  await page.getByRole("button", { name: "Envoyer la pièce" }).click();
  await expect(page.getByText("À refaire")).toBeVisible({ timeout: 30_000 });

  await page.getByRole("button", { name: /Aide sur mes pièces/ }).click();
  await expect(page.getByRole("log")).toContainText("n'a pas pu être lu");
  await page.getByLabel("Votre message").fill("Pourquoi ma facture est refusée ?");
  await page.getByRole("button", { name: "Envoyer" }).click();
  await expect(page.getByRole("log").locator("li").filter({ hasText: "n'a pas pu être lu" })).toHaveCount(2, { timeout: 15_000 });
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
  await expect(page.locator("body")).not.toContainText(/fraude|partenaire|repli|score/i);
});

test("la page de connexion est accessible (desktop et mobile)", async ({ page }) => {
  await page.goto("/connexion");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
});

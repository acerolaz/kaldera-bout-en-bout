import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import { DOSSIER_ACCEPTE, DOSSIER_DEGRADE, DOSSIER_EN_COURS } from "@/test/fixtures";
import { FauxEventSource, simulerFlux } from "@/test/flux";
import { json, rendre, simulerApi } from "@/test/rendre";
import { Dossier } from "./Dossier";

afterEach(() => vi.unstubAllGlobals());

const ouvrir = (reference: string) =>
  rendre(
    <Routes>
      <Route path="/demandes/:reference" element={<Dossier />} />
    </Routes>,
    `/demandes/${reference}`,
  );

describe("E2 · Dossier", () => {
  it("en cours : étape courante, % agent en direct, région annoncée", async () => {
    simulerFlux();
    simulerApi(() => json(DOSSIER_EN_COURS));
    ouvrir("KAL-26-0101");
    expect(await screen.findByRole("progressbar", { name: "Avancement de l'étape Pièces" })).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText("Étape en cours : Pièces")).toBeInTheDocument();
    const source = FauxEventSource.instances[0];
    expect(source.url).toBe("/api/flux/demandes/KAL-26-0101");
    source.emettre({ type: "sous_etape", reference: "KAL-26-0101", etat: "pieces", statut: "en_cours", avancement_agent: 50 });
    // notification TanStack asynchrone
    await waitFor(() => expect(screen.getByRole("progressbar", { name: "Avancement de l'étape Pièces" })).toHaveAttribute("aria-valuenow", "50"));
    source.couper();
    expect(screen.getByText("Reconnexion…")).toBeInTheDocument();
  });

  it("terminal : aucun flux", async () => {
    simulerFlux();
    simulerApi(() => json(DOSSIER_ACCEPTE));
    ouvrir("KAL-26-0101");
    await screen.findByText("Martin Claire");
    expect(FauxEventSource.instances).toHaveLength(0);
    expect(screen.getByText("Traitement terminé")).toBeInTheDocument();
  });

  it("en-tête : titre, assuré, issue, avancement et durée sur le budget", async () => {
    simulerApi(() => json(DOSSIER_ACCEPTE));
    ouvrir("KAL-26-0101");
    expect(screen.getByRole("heading", { level: 1, name: "Dossier KAL-26-0101" })).toBeInTheDocument();
    expect(await screen.findByText("Martin Claire")).toBeInTheDocument();
    expect(screen.getByText("CTR-778801")).toBeInTheDocument();
    expect(screen.getByText("Acceptée")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Avancement du dossier" })).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByText("2,4 s / 8 s")).toBeInTheDocument();
    expect(screen.getByText(/1\s230,00\s€/)).toBeInTheDocument();
  });

  it("timeline : 5 étapes ordonnées, statuts et résumés", async () => {
    simulerApi(() => json(DOSSIER_DEGRADE));
    ouvrir("KAL-26-0203");
    const timeline = await screen.findByRole("list", { name: "Étapes du traitement" });
    const cartes = within(timeline).getAllByRole("listitem");
    expect(cartes.map((c) => within(c).getByRole("heading").textContent)).toEqual([
      "Éligibilité", "Pièces", "Estimation", "Anti-fraude", "Décision",
    ]);
    expect(within(cartes[2]).getByText("Repli déterministe")).toBeInTheDocument();
    expect(within(cartes[2]).getByText(/repli \(disjoncteur\)/)).toBeInTheDocument();
    expect(within(cartes[3]).getByText("Mode dégradé")).toBeInTheDocument();
    expect(within(cartes[4]).getByText("En attente")).toBeInTheDocument();
    expect(cartes[4]).not.toHaveTextContent(/NaN|null/);
  });

  it("carte anti-fraude détaillée et borne atteinte", async () => {
    simulerApi(() => json(DOSSIER_DEGRADE));
    ouvrir("KAL-26-0203");
    const carte = await screen.findByRole("region", { name: "Carte anti-fraude" });
    expect(within(carte).getByText("Requis").nextElementSibling).toHaveTextContent("oui");
    expect(carte).toHaveTextContent("F2, F4");
    expect(carte).toHaveTextContent("Indisponible");
    expect(carte).toHaveTextContent("transport:timeout");
    expect(screen.getByText("Borne atteinte")).toBeInTheDocument();
  });

  it("score anti-fraude à virgule décimale et étape sautée sans durée", async () => {
    const [eligibilite, pieces, ...suite] = DOSSIER_ACCEPTE.etapes;
    simulerApi(() =>
      json({
        ...DOSSIER_ACCEPTE,
        etapes: [eligibilite, { ...pieces, statut: "sautee", duree_ms: 0, resume: "Sautée (garde ok)" }, ...suite],
        antifraude: { ...DOSSIER_ACCEPTE.antifraude!, requis: true, statut: "ok", score: 0.75 },
      }),
    );
    ouvrir("KAL-26-0101");
    const carte = await screen.findByRole("region", { name: "Carte anti-fraude" });
    expect(carte).toHaveTextContent("0,75");
    const cartePieces = within(screen.getByRole("list", { name: "Étapes du traitement" })).getAllByRole("listitem")[1];
    expect(cartePieces).not.toHaveTextContent(/\d ms/);
  });

  it("Garanties : panneau au clavier, Échap ferme et rend le focus", async () => {
    simulerApi(() => json(DOSSIER_ACCEPTE));
    ouvrir("KAL-26-0101");
    const bouton = await screen.findByRole("button", { name: "Garanties" });
    bouton.focus();
    await userEvent.keyboard("{Enter}");
    const panneau = await screen.findByRole("dialog", { name: "Garanties" });
    expect(panneau).toHaveTextContent("confort");
    expect(panneau).toHaveTextContent(/150,00\s€/);
    expect(panneau).toHaveTextContent(/8\s000,00\s€/);
    expect(panneau).toHaveTextContent("extraction_vlm");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(bouton).toHaveFocus();
  });

  it("référence inconnue : « Dossier introuvable. » et retour", async () => {
    simulerApi(() => json({ detail: "demande inconnue" }, 404));
    ouvrir("KAL-26-9999");
    expect(await screen.findByText("Dossier introuvable.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Dossier KAL-26-9999" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Retour à la liste des demandes" })).toHaveAttribute("href", "/");
  });

  it("chargement annoncé aux lecteurs d'écran", async () => {
    simulerApi(() => new Promise(() => {}));
    ouvrir("KAL-26-0101");
    expect(screen.getByRole("status")).toHaveTextContent("Chargement du dossier…");
  });

  it("API en panne : alerte et Réessayer", async () => {
    let panne = true;
    simulerApi(() => (panne ? json({ detail: "base indisponible" }, 503) : json(DOSSIER_ACCEPTE)));
    ouvrir("KAL-26-0101");
    expect(await screen.findByRole("alert")).toHaveTextContent("base indisponible");
    panne = false;
    await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByText("Martin Claire")).toBeInTheDocument();
    expect(screen.getByTestId("dossier")).toHaveFocus();
  });

  it("n'a aucune violation axe", async () => {
    simulerApi(() => json(DOSSIER_DEGRADE));
    const { container } = ouvrir("KAL-26-0203");
    await screen.findByRole("list", { name: "Étapes du traitement" });
    expect(await axe(container)).toHaveNoViolations();
  });
});

import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import { LOT } from "@/test/fixtures";
import { FauxEventSource, simulerFlux } from "@/test/flux";
import { json, rendre, simulerApi } from "@/test/rendre";
import { Lot } from "./Lot";

beforeEach(simulerFlux);
afterEach(() => vi.unstubAllGlobals());

const ouvrir = (id: string) =>
  rendre(<Routes><Route path="/lots/:id" element={<Lot />} /></Routes>, `/lots/${id}`);

describe("E3 · Suivi de lot", () => {
  it("en-tête : avancement, compteurs, durée écoulée", async () => {
    simulerApi(() => json(LOT));
    ouvrir("7");
    expect(screen.getByRole("heading", { level: 1, name: "Lot 7" })).toBeInTheDocument();
    expect(await screen.findByRole("progressbar", { name: "Avancement du lot" })).toHaveAttribute("aria-valuenow", "50");
    const entete = screen.getByRole("region", { name: "En-tête du lot" });
    expect(within(entete).getByText("Acceptées").nextElementSibling).toHaveTextContent("1");
    expect(within(entete).getByText("Escaladées").nextElementSibling).toHaveTextContent("cellule_fraude 1");
    expect(within(entete).getByText("Modes dégradés").nextElementSibling).toHaveTextContent("1");
    expect(within(entete).getByText("Durée écoulée")).toBeInTheDocument();
  });

  it("une ligne par dossier : barre, étape en cours, badges, lien vers E2", async () => {
    simulerApi(() => json(LOT));
    ouvrir("7");
    const ligne = (await screen.findByRole("link", { name: "KAL-26-0106" })).closest("tr")!;
    expect(screen.getByRole("link", { name: "KAL-26-0106" })).toHaveAttribute("href", "/demandes/KAL-26-0106");
    expect(within(ligne).getByRole("progressbar", { name: "Avancement de KAL-26-0106" })).toHaveAttribute("aria-valuenow", "100");
    expect(within(ligne).getByText("Mode dégradé")).toBeInTheDocument();
    expect(within(ligne).getByText("Borne atteinte")).toBeInTheDocument();
    const enCours = screen.getByRole("link", { name: "KAL-26-0105" }).closest("tr")!;
    expect(within(enCours).getByText("Estimation")).toBeInTheDocument();
  });

  it("une sous-étape ne met à jour que sa ligne ; fin d'étape ⇒ relecture", async () => {
    const espion = simulerApi(() => json(LOT));
    ouvrir("7");
    await screen.findByRole("link", { name: "KAL-26-0105" });
    const source = FauxEventSource.instances[0];
    expect(source.url).toBe("/api/flux/lots/7");
    source.emettre({ type: "etape_debut", reference: "KAL-26-0107", etat: "pieces", statut: "en_cours", avancement_agent: 0 });
    const ligne107 = screen.getByRole("link", { name: "KAL-26-0107" }).closest("tr")!;
    const ligne105 = screen.getByRole("link", { name: "KAL-26-0105" }).closest("tr")!;
    expect(await within(ligne107).findByText("Pièces")).toBeInTheDocument(); // notification react-query asynchrone
    expect(within(ligne105).getByText("Estimation")).toBeInTheDocument();
    const appels = espion.mock.calls.length;
    source.emettre({ type: "etape_fin", reference: "KAL-26-0107", etat: "pieces", statut: null, avancement_agent: 100 });
    await vi.waitFor(() => expect(espion.mock.calls.length).toBeGreaterThan(appels));
  });

  it("lot terminé : aucun flux", async () => {
    simulerApi(() => json({ ...LOT, avancement: 100, fin: "2026-10-12T09:00:09Z" }));
    ouvrir("7");
    await screen.findByRole("link", { name: "KAL-26-0104" });
    expect(FauxEventSource.instances).toHaveLength(0);
    expect(screen.getByText("9 s")).toBeInTheDocument();
  });

  it.each([["999", 404], ["abc", 422]])("lot inconnu ou identifiant invalide (%s)", async (id, statut) => {
    simulerApi(() => json({ detail: "lot inconnu" }, statut));
    ouvrir(id);
    expect(await screen.findByText("Lot introuvable.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Retour à la liste des demandes" })).toHaveAttribute("href", "/");
  });

  it("API en panne : alerte et Réessayer", async () => {
    simulerApi(() => json({ detail: "base indisponible" }, 503));
    ouvrir("7");
    expect(await screen.findByRole("alert")).toHaveTextContent("base indisponible");
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });

  it("flux coupé : « Reconnexion… »", async () => {
    simulerApi(() => json(LOT));
    ouvrir("7");
    await screen.findByRole("link", { name: "KAL-26-0105" });
    FauxEventSource.instances[0].couper();
    expect(screen.getByText("Reconnexion…")).toBeInTheDocument();
  });

  it("n'a aucune violation axe", async () => {
    simulerApi(() => json(LOT));
    const { container } = ouvrir("7");
    await screen.findByRole("link", { name: "KAL-26-0105" });
    expect(await axe(container)).toHaveNoViolations();
  });
});

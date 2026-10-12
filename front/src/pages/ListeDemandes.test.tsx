import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import { LIGNES } from "@/test/fixtures";
import { json, rendre, simulerApi } from "@/test/rendre";
import { ListeDemandes } from "./ListeDemandes";

afterEach(() => vi.unstubAllGlobals());

const avecLignes = () => simulerApi(() => json(LIGNES));

describe("E1 · Liste des demandes", () => {
  it("affiche les colonnes, les statuts (icône + libellé) et un lien vers E2", async () => {
    avecLignes();
    rendre(<ListeDemandes />);
    const lien = await screen.findByRole("link", { name: "KAL-26-0203" });
    expect(lien).toHaveAttribute("href", "/demandes/KAL-26-0203");
    const ligne = lien.closest("tr")!;
    expect(within(ligne).getByText("Durand Paul")).toBeInTheDocument();
    expect(within(ligne).getByText("CTR-778803")).toBeInTheDocument();
    expect(within(ligne).getByText(/9\s200,00\s€/)).toBeInTheDocument();
    expect(within(ligne).getByText("Escaladée")).toBeInTheDocument();
    expect(within(ligne).getByText("Mode dégradé")).toBeInTheDocument();
    expect(within(ligne).getByText("cellule_fraude")).toBeInTheDocument();
  });

  it("champ absent : « — », jamais NaN ni null", async () => {
    avecLignes();
    rendre(<ListeDemandes />);
    const ligne = (await screen.findByRole("link", { name: "KAL-26-0101" })).closest("tr")!;
    expect(within(ligne).getAllByText("—").length).toBeGreaterThanOrEqual(2); // montant, issue
    expect(ligne).not.toHaveTextContent(/NaN|null/);
  });

  it("filtres : reflétés dans l'URL et transmis à l'API", async () => {
    const espion = avecLignes();
    rendre(<ListeDemandes />);
    await screen.findByRole("link", { name: "KAL-26-0203" });
    await userEvent.selectOptions(screen.getByLabelText("Issue"), "escalade");
    expect(screen.getByTestId("url")).toHaveTextContent("/?issue=escalade");
    expect(espion).toHaveBeenCalledWith("/api/demandes?issue=escalade");
    await userEvent.click(screen.getByLabelText("Mode dégradé seulement"));
    await userEvent.type(screen.getByLabelText("Recherche"), "durand{Enter}");
    expect(screen.getByTestId("url")).toHaveTextContent("/?issue=escalade&mode_degrade=true&q=durand");
    expect(espion).toHaveBeenLastCalledWith("/api/demandes?issue=escalade&mode_degrade=true&q=durand");
  });

  it("la recherche garde le focus et l'URL est canonique", async () => {
    avecLignes();
    rendre(<ListeDemandes />);
    await screen.findByRole("link", { name: "KAL-26-0203" });
    const champ = screen.getByLabelText("Recherche");
    await userEvent.type(champ, "durand{Enter}");
    expect(document.activeElement).toBe(champ);
    await userEvent.selectOptions(screen.getByLabelText("Issue"), "escalade");
    await userEvent.selectOptions(screen.getByLabelText("Statut"), "terminee");
    expect(screen.getByTestId("url")).toHaveTextContent("/?statut=terminee&issue=escalade&q=durand");
  });

  it("les options de file viennent des données", async () => {
    avecLignes();
    rendre(<ListeDemandes />);
    await screen.findByRole("link", { name: "KAL-26-0203" });
    const options = within(screen.getByLabelText("File")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Toutes", "cellule_fraude"]);
  });

  it("une file de l'URL absente des données reste sélectionnée", async () => {
    avecLignes();
    rendre(<ListeDemandes />, "/?file=archives");
    await screen.findByRole("link", { name: "KAL-26-0203" });
    expect(screen.getByLabelText("File")).toHaveValue("archives");
  });

  it("filtres sans résultat : message et « Effacer les filtres »", async () => {
    simulerApi((url) => json(url === "/api/demandes" ? LIGNES : []));
    rendre(<ListeDemandes />, "/?statut=secours");
    expect(await screen.findByText("Aucune demande ne correspond aux filtres.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Effacer les filtres" }));
    expect(screen.getByTestId("url")).toHaveTextContent(/^\/$/);
    expect(document.activeElement).not.toBe(document.body);
    expect(await screen.findByRole("link", { name: "KAL-26-0203" })).toBeInTheDocument();
  });

  it("base vide : renvoie vers make demo", async () => {
    simulerApi(() => json([]));
    rendre(<ListeDemandes />);
    expect(await screen.findByText(/Aucune demande en base/)).toHaveTextContent(
      "Aucune demande en base : lancer make demo puis make scenarios.",
    );
  });

  it("API en panne : alerte et Réessayer", async () => {
    let panne = true;
    simulerApi(() => (panne ? json({ detail: "base indisponible" }, 503) : json(LIGNES)));
    rendre(<ListeDemandes />);
    expect(await screen.findByRole("alert")).toHaveTextContent("base indisponible");
    panne = false;
    await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByRole("link", { name: "KAL-26-0203" })).toBeInTheDocument();
  });

  it("chargement : zone aria-busy", () => {
    simulerApi(() => new Promise<Response>(() => {}));
    rendre(<ListeDemandes />);
    expect(screen.getByTestId("liste")).not.toHaveAttribute("aria-busy");
    expect(screen.getByRole("status").nextElementSibling).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Chargement des demandes…");
  });

  it("n'a aucune violation axe", async () => {
    avecLignes();
    const { container } = rendre(<ListeDemandes />);
    await screen.findByRole("link", { name: "KAL-26-0203" });
    expect(await axe(container)).toHaveNoViolations();
  });
});

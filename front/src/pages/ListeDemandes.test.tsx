import { screen, waitFor, within } from "@testing-library/react";
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

  it("seuls les dossiers prêts sont sélectionnables ; le motif est lisible au clavier", async () => {
    avecLignes();
    rendre(<ListeDemandes />);
    const bloquee = await screen.findByRole("checkbox", { name: "Sélectionner KAL-26-0101" });
    expect(bloquee).toBeDisabled();
    expect(bloquee).toHaveAccessibleDescription("Pièces en cours d'analyse");
    expect(bloquee).toHaveAttribute("title", "Pièces en cours d'analyse");
    expect(screen.getByRole("checkbox", { name: "Sélectionner KAL-26-0104" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Traiter la sélection (0)" })).toBeDisabled();
  });

  it("tout sélectionner coche les dossiers prêts visibles", async () => {
    avecLignes();
    rendre(<ListeDemandes />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Tout sélectionner" }));
    expect(screen.getByRole("button", { name: "Traiter la sélection (2)" })).toBeEnabled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Tout sélectionner" }));
    expect(screen.getByRole("button", { name: "Traiter la sélection (0)" })).toBeDisabled();
  });

  const lancement = (reponse: Response) =>
    simulerApi((_url, init) => (init?.method === "POST" ? reponse : json(LIGNES)));

  it("1 dossier ⇒ E2", async () => {
    const espion = lancement(json({ lot_id: 7, references: ["KAL-26-0104"] }, 202));
    rendre(<ListeDemandes />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Sélectionner KAL-26-0104" }));
    await userEvent.click(screen.getByRole("button", { name: "Traiter la sélection (1)" }));
    await waitFor(() => expect(screen.getByTestId("url")).toHaveTextContent(/^\/demandes\/KAL-26-0104$/));
    expect(espion).toHaveBeenCalledWith("/api/traitements", expect.objectContaining({
      method: "POST", body: '{"references":["KAL-26-0104"]}',
    }));
  });

  it("N dossiers ⇒ E3", async () => {
    lancement(json({ lot_id: 7, references: ["KAL-26-0105", "KAL-26-0104"] }, 202));
    rendre(<ListeDemandes />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Tout sélectionner" }));
    await userEvent.click(screen.getByRole("button", { name: "Traiter la sélection (2)" }));
    await waitFor(() => expect(screen.getByTestId("url")).toHaveTextContent(/^\/lots\/7$/));
  });

  it("409 : alerte avec les dossiers refusés", async () => {
    lancement(json({ detail: "dossiers non lançables", references: ["KAL-26-0104"] }, 409));
    rendre(<ListeDemandes />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Sélectionner KAL-26-0104" }));
    await userEvent.click(screen.getByRole("button", { name: "Traiter la sélection (1)" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Impossible de lancer le traitement : dossiers non lançables : KAL-26-0104",
    );
  });

  it("changer de filtre vide la sélection", async () => {
    avecLignes();
    rendre(<ListeDemandes />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Sélectionner KAL-26-0104" }));
    await userEvent.selectOptions(screen.getByLabelText("Statut"), "prete");
    expect(await screen.findByRole("button", { name: "Traiter la sélection (0)" })).toBeDisabled();
  });

  it("après un 409, les dossiers devenus non lançables sortent de la sélection", async () => {
    let refuse = false;
    simulerApi((_url, init) => {
      if (init?.method === "POST") {
        refuse = true;
        return json({ detail: "dossiers non lançables", references: ["KAL-26-0104"] }, 409);
      }
      return json(LIGNES.map((l) => (refuse && l.reference === "KAL-26-0104"
        ? { ...l, selectionnable: false, motif_non_selectionnable: "Traitement en cours" } : l)));
    });
    rendre(<ListeDemandes />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Tout sélectionner" }));
    await userEvent.click(screen.getByRole("button", { name: "Traiter la sélection (2)" }));
    expect(await screen.findByRole("button", { name: "Traiter la sélection (1)" })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: "Sélectionner KAL-26-0104" })).not.toBeChecked();
  });
});

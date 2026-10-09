import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import type { VueDemande } from "../api";
import { VUE } from "../test/donnees";
import { Depot, type DepotHandle } from "./Depot";
import { ListePieces } from "./ListePieces";
import { Soumettre } from "./Soumettre";
import { Stepper } from "./Stepper";
import { VerdictCarte } from "./VerdictCarte";

afterEach(() => vi.unstubAllGlobals());
const repondre = (statut: number, corps: unknown) =>
  vi.fn((_url?: string, _init?: RequestInit) => Promise.resolve(new Response(JSON.stringify(corps), { status: statut })));

describe("Stepper", () => {
  it("étape courante, branche, horodatage, accessible", async () => {
    const { container } = render(<Stepper vue={{ ...VUE, etape: 3, branche: null, horodatages: { "1": VUE.cree_le, "2": VUE.cree_le } }} />);
    const courante = screen.getByText("Évaluation du dommage").closest("li");
    expect(courante).toHaveAttribute("aria-current", "step");
    expect(container.querySelectorAll("time")).toHaveLength(2);
    expect(await axe(container)).toHaveNoViolations();
  });
  it("branche « transmise » sans rouge ni détail", () => {
    render(<Stepper vue={{ ...VUE, etape: 5, branche: "gestionnaire" }} />);
    expect(screen.getByText("Transmise à un gestionnaire")).toBeInTheDocument();
    expect(document.body.innerHTML).not.toMatch(/destructive|fraude/);
  });
});

describe("ListePieces", () => {
  it("statut écrit en toutes lettres, raison, bouton Déposer", async () => {
    const onDeposer = vi.fn();
    const { container } = render(
      <ListePieces
        pieces={[
          { type: "facture", libelle: "Facture", statut: "a_refaire", raison: "Illisible." },
          { type: "photo", libelle: "Photos des dommages", statut: "validee", raison: null },
        ]}
        onDeposer={onDeposer}
      />,
    );
    expect(screen.getByText("À refaire")).toBeInTheDocument();
    expect(screen.getByText("Illisible.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Déposer : Facture" }));
    expect(onDeposer).toHaveBeenCalledWith("facture");
    expect(screen.queryByRole("button", { name: "Déposer : Photos des dommages" })).toBeNull();
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("Depot", () => {
  const fichier = new File(["%PDF-1.4"], "facture.pdf", { type: "application/pdf" });

  it("dépose, avertit d'un PDF multipage, accessible", async () => {
    vi.stubGlobal("fetch", repondre(202, { statut: "recu", avertissement_multipage: true }));
    const onDepose = vi.fn();
    const { container } = render(
      <Depot reference="KAL-26-0101" type="facture" onTypeChange={() => {}} onDepose={onDepose} />,
    );
    await userEvent.upload(screen.getByLabelText("Choisir un fichier"), fichier);
    await userEvent.click(screen.getByRole("button", { name: "Envoyer la pièce" }));
    expect(await screen.findByText(/seule la première sera lue/)).toBeInTheDocument();
    expect(onDepose).toHaveBeenCalled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it.each([
    [415, "Format non accepté : PDF, PNG ou JPEG uniquement."],
    [409, "Votre dossier a déjà été soumis : il n'est plus possible d'ajouter de pièce."],
  ])("erreur %s annoncée sous la zone", async (statut, message) => {
    vi.stubGlobal("fetch", repondre(statut, { detail: "x" }));
    render(<Depot reference="KAL-26-0101" type="photo" onTypeChange={() => {}} onDepose={() => {}} />);
    await userEvent.upload(screen.getByLabelText("Choisir un fichier"), fichier);
    await userEvent.click(screen.getByRole("button", { name: "Envoyer la pièce" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("session expirée (401) : prévient la page, sans message d'erreur", async () => {
    vi.stubGlobal("fetch", repondre(401, { detail: "session requise" }));
    const onExpire = vi.fn();
    render(<Depot reference="R" type="photo" onTypeChange={() => {}} onDepose={() => {}} onExpire={onExpire} />);
    await userEvent.upload(screen.getByLabelText("Choisir un fichier"), fichier);
    await userEvent.click(screen.getByRole("button", { name: "Envoyer la pièce" }));
    await waitFor(() => expect(onExpire).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("focus() amène la zone de dépôt", () => {
    const ref = createRef<DepotHandle>();
    render(<Depot ref={ref} reference="R" type="facture" onTypeChange={() => {}} onDepose={() => {}} />);
    ref.current?.focus();
    expect(screen.getByLabelText("Type de pièce")).toHaveFocus();
  });
});

describe("Soumettre", () => {
  const complete: VueDemande = { ...VUE, branche: null, pieces: [{ type: "facture", libelle: "Facture", statut: "validee", raison: null }] };

  it("désactivé pendant une analyse, avec la raison écrite", () => {
    render(<Soumettre vue={{ ...VUE, pieces: [{ ...VUE.pieces[0], statut: "en_analyse" }] }} onSoumise={() => {}} />);
    expect(screen.getByRole("button", { name: "Soumettre mon dossier" })).toBeDisabled();
    expect(screen.getByText("Patientez : une pièce est encore en analyse.")).toBeInTheDocument();
  });

  it("pièces manquantes : confirmation puis envoi avec confirmer", async () => {
    const appel = repondre(200, { ...VUE, soumise: true });
    vi.stubGlobal("fetch", appel);
    const onSoumise = vi.fn();
    render(<Soumettre vue={VUE} onSoumise={onSoumise} />);
    await userEvent.click(screen.getByRole("button", { name: "Soumettre mon dossier" }));
    await userEvent.click(await screen.findByRole("button", { name: "Soumettre quand même" }));
    await waitFor(() => expect(onSoumise).toHaveBeenCalled());
    expect(JSON.parse(String(appel.mock.calls[0][1]?.body))).toEqual({ confirmer: true });
  });

  it("double soumission : 409 deja_soumise sans message d'erreur", async () => {
    vi.stubGlobal("fetch", repondre(409, { detail: "deja_soumise" }));
    render(<Soumettre vue={complete} onSoumise={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Soumettre mon dossier" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(await screen.findByText("Dossier soumis.")).toBeInTheDocument();
  });

  it("session expirée (401) : prévient la page", async () => {
    vi.stubGlobal("fetch", repondre(401, { detail: "session requise" }));
    const onExpire = vi.fn();
    render(<Soumettre vue={complete} onSoumise={() => {}} onExpire={onExpire} />);
    await userEvent.click(screen.getByRole("button", { name: "Soumettre mon dossier" }));
    await waitFor(() => expect(onExpire).toHaveBeenCalled());
  });
});

describe("VerdictCarte", () => {
  it("montant et franchise en euros, accessible", async () => {
    const { container } = render(
      <VerdictCarte verdict={{ issue: "acceptee", montant: 1700, franchise: 150, explication: "Montant retenu…", pieces_retenues: ["Facture"] }} />,
    );
    expect(screen.getByRole("heading", { name: "Décision" })).toBeInTheDocument();
    expect(screen.getByText(/1\s700,00\s€/)).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
  it("transmise : ni montant ni franchise", () => {
    render(<VerdictCarte verdict={{ issue: "transmise", montant: null, franchise: null, explication: "Transmis.", pieces_retenues: [] }} />);
    expect(screen.queryByText("Montant remboursé")).toBeNull();
  });
});

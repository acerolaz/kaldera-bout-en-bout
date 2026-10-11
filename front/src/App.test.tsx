import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import { Routage } from "./App";

const ouvrir = (chemin: string) =>
  render(
    <MemoryRouter initialEntries={[chemin]}>
      <Routage />
    </MemoryRouter>,
  );

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
});

describe("socle", () => {
  it.each([
    ["/", "Liste des demandes"],
    ["/demandes/KAL-26-0101", "Dossier KAL-26-0101"],
    ["/lots/1", "Lot 1"],
    ["/nulle-part", "Page introuvable"],
  ])("%s affiche son titre", (chemin, titre) => {
    ouvrir(chemin);
    expect(screen.getByRole("heading", { level: 1, name: titre })).toBeInTheDocument();
    expect(document.title).toBe(`Kaldera · ${titre}`);
  });

  it("la 404 ramène à la liste", () => {
    ouvrir("/nulle-part");
    expect(screen.getByRole("link", { name: "Retour à la liste des demandes" })).toHaveAttribute("href", "/");
  });

  it("en-tête : marque, lien Demandes courant, lien d'évitement en premier", async () => {
    ouvrir("/");
    expect(screen.getByText("Kaldera · back-office gestionnaire")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Demandes" })).toHaveAttribute("aria-current", "page");
    await userEvent.tab();
    expect(screen.getByRole("link", { name: "Aller au contenu" })).toHaveFocus();
  });

  it("le bouton de thème bascule et change son libellé", async () => {
    ouvrir("/");
    await userEvent.click(screen.getByRole("button", { name: "Passer au thème sombre" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("button", { name: "Passer au thème clair" })).toBeInTheDocument();
  });

  it("n'a aucune violation axe", async () => {
    const { container } = ouvrir("/");
    expect(await axe(container)).toHaveNoViolations();
  });
});

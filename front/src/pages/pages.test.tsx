import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import { VUE } from "../test/donnees";
import { Connexion } from "./Connexion";
import { MesSinistres } from "./MesSinistres";
import { Sinistre } from "./Sinistre";

afterEach(() => vi.unstubAllGlobals());
const repondre = (statut: number, corps: unknown) =>
  vi.fn(() => Promise.resolve(new Response(statut === 204 ? null : JSON.stringify(corps), { status: statut })));

function dans(chemin: string, element: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[chemin]}>
      <Routes>
        <Route path="/connexion" element={<p>page de connexion</p>} />
        <Route path="/" element={<p>mes sinistres</p>} />
        <Route path="*" element={element} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Connexion", () => {
  it("erreur annoncée, accessible", async () => {
    vi.stubGlobal("fetch", repondre(401, { detail: "x" }));
    const { container } = dans("/c", <Connexion />);
    await userEvent.type(screen.getByLabelText("Identifiant"), "claire");
    await userEvent.type(screen.getByLabelText("Mot de passe"), "faux");
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Identifiant ou mot de passe incorrect");
    expect(await axe(container)).toHaveNoViolations();
  });
  it("succès : vers mes sinistres", async () => {
    vi.stubGlobal("fetch", repondre(204, null));
    dans("/c", <Connexion />);
    await userEvent.type(screen.getByLabelText("Identifiant"), "claire");
    await userEvent.type(screen.getByLabelText("Mot de passe"), "bon");
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByText("mes sinistres")).toBeInTheDocument();
  });
});

describe("MesSinistres", () => {
  it("liste les dossiers en liens", async () => {
    vi.stubGlobal("fetch", repondre(200, [{ reference: "KAL-26-0101", cree_le: "2026-10-09T10:00:00Z", etape: 1, branche: "attente_pieces" }]));
    dans("/liste", <MesSinistres />);
    expect(await screen.findByRole("link", { name: /Sinistre KAL-26-0101/ })).toHaveAttribute("href", "/sinistres/KAL-26-0101");
  });
});

describe("Sinistre", () => {
  it("session expirée : retour à la connexion", async () => {
    vi.stubGlobal("fetch", repondre(401, { detail: "session requise" }));
    vi.stubGlobal("EventSource", class { addEventListener() {} close() {} onerror = null; onopen = null; });
    dans("/sinistres/KAL-26-0101", <Sinistre reference="KAL-26-0101" />);
    await waitFor(() => expect(screen.getByText("page de connexion")).toBeInTheDocument());
  });
  it("dossier soumis : pas de bouton Déposer pour une pièce à fournir", async () => {
    const soumise = { ...VUE, soumise: true, branche: "gestionnaire", etape: 5 };
    vi.stubGlobal("fetch", repondre(200, soumise));
    vi.stubGlobal("EventSource", class { addEventListener() {} close() {} onerror = null; onopen = null; });
    dans("/sinistres/KAL-26-0101", <Sinistre reference="KAL-26-0101" />);
    expect(await screen.findByText("À fournir")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Déposer/ })).toBeNull();
  });
  it("dossier introuvable (404) : message, pas de page blanche", async () => {
    vi.stubGlobal("fetch", repondre(404, { detail: "introuvable" }));
    vi.stubGlobal("EventSource", class { addEventListener() {} close() {} onerror = null; onopen = null; });
    dans("/sinistres/KAL-26-9999", <Sinistre reference="KAL-26-9999" />);
    expect(await screen.findByText("Ce dossier est introuvable.")).toBeInTheDocument();
  });
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import type { MessageChat } from "../api";
import { Chat } from "./Chat";

afterEach(() => vi.unstubAllGlobals());
const MESSAGES: MessageChat[] = [
  { auteur: "agent", texte: "Ce document n'a pas pu être lu : facture.", actions: ["deposer"] },
  { auteur: "assure", texte: "Pourquoi ?", actions: [] },
];
const repondre = (statut: number, corps: unknown) =>
  vi.fn((_url?: string, _init?: RequestInit) => Promise.resolve(new Response(JSON.stringify(corps), { status: statut })));
const ouvrir = () => userEvent.click(screen.getByRole("button", { name: /Aide sur mes pièces/ }));
const ecrireEtEnvoyer = async (texte: string) => {
  await ouvrir();
  await userEvent.type(await screen.findByLabelText("Votre message"), texte);
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
};

describe("Chat", () => {
  it("s'ouvre, affiche le journal, accessible", async () => {
    const { baseElement } = render(<Chat reference="R" messages={MESSAGES} onDeposer={() => {}} />);
    await ouvrir();
    const journal = await screen.findByRole("log");
    expect(journal).toHaveTextContent("Ce document n'a pas pu être lu");
    expect(journal).toHaveTextContent("Pourquoi ?");
    expect(await axe(baseElement)).toHaveNoViolations();
  });

  it("envoi désactivé si le message est vide ou fait d'espaces", async () => {
    render(<Chat reference="R" messages={[]} onDeposer={() => {}} />);
    await ouvrir();
    const envoyer = await screen.findByRole("button", { name: "Envoyer" });
    expect(envoyer).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Votre message"), "   ");
    expect(envoyer).toBeDisabled();
  });

  it("envoie le message et vide le champ", async () => {
    const appel = repondre(202, { auteur: "agent", texte: "ok", actions: [] });
    vi.stubGlobal("fetch", appel);
    render(<Chat reference="KAL-26-0101" messages={[]} onDeposer={() => {}} />);
    await ouvrir();
    const champ = await screen.findByLabelText("Votre message");
    await userEvent.type(champ, "Quelles pièces ?");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    await waitFor(() => expect(champ).toHaveValue(""));
    expect(appel.mock.calls[0][0]).toBe("/assure/demandes/KAL-26-0101/messages");
  });

  it("action rapide « Déposer maintenant » ferme et amène au dépôt", async () => {
    const onDeposer = vi.fn();
    render(<Chat reference="R" messages={MESSAGES} onDeposer={onDeposer} />);
    await ouvrir();
    await userEvent.click(await screen.findByRole("button", { name: "Déposer maintenant" }));
    await waitFor(() => expect(onDeposer).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("log")).toBeNull());
  });

  it("sans onDeposer (dépôt impossible), l'action rapide n'est pas affichée", async () => {
    render(<Chat reference="R" messages={MESSAGES} />);
    await ouvrir();
    await screen.findByRole("log");
    expect(screen.queryByRole("button", { name: "Déposer maintenant" })).toBeNull();
  });

  it("à la fermeture, le focus revient au bouton d'ouverture", async () => {
    render(<Chat reference="R" messages={[]} onDeposer={() => {}} />);
    await ouvrir();
    await userEvent.click(await screen.findByRole("button", { name: "Fermer" }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Aide sur mes pièces/ })).toHaveFocus());
  });

  it("signale un nouveau message de l'assistant quand le chat est fermé, puis plus une fois lu", async () => {
    render(<Chat reference="R" messages={MESSAGES.slice(0, 1)} onDeposer={() => {}} />);
    expect(screen.getByRole("button", { name: /nouveau message/ })).toBeInTheDocument();
    await ouvrir();
    await userEvent.click(await screen.findByRole("button", { name: "Fermer" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Aide sur mes pièces" })).toBeInTheDocument());
  });

  it("429 : message « trop de messages », texte conservé", async () => {
    vi.stubGlobal("fetch", repondre(429, { detail: "trop de messages pour ce dossier" }));
    render(<Chat reference="R" messages={[]} onDeposer={() => {}} />);
    await ecrireEtEnvoyer("Bonjour");
    expect(await screen.findByRole("alert")).toHaveTextContent("trop de messages");
    expect(screen.getByLabelText("Votre message")).toHaveValue("Bonjour");
  });

  it("session expirée (401) : prévient la page, sans message d'erreur", async () => {
    vi.stubGlobal("fetch", repondre(401, { detail: "session requise" }));
    const onExpire = vi.fn();
    render(<Chat reference="R" messages={[]} onDeposer={() => {}} onExpire={onExpire} />);
    await ecrireEtEnvoyer("Bonjour");
    await waitFor(() => expect(onExpire).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("réseau coupé : erreur par défaut annoncée", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    render(<Chat reference="R" messages={[]} onDeposer={() => {}} />);
    await ecrireEtEnvoyer("Bonjour");
    expect(await screen.findByRole("alert")).toHaveTextContent("Message non envoyé. Réessayez.");
  });
});

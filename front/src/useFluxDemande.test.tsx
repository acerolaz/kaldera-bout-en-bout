import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VUE } from "./test/donnees";
import { useFluxDemande } from "./useFluxDemande";

class FauxFlux {
  ecouteurs: Record<string, ((e: MessageEvent) => void)[]> = {};
  ferme = false;
  onerror: (() => void) | null = null;
  onopen: (() => void) | null = null;
  constructor(public url: string) {}
  addEventListener(type: string, f: (e: MessageEvent) => void) {
    (this.ecouteurs[type] ??= []).push(f);
  }
  emettre(type: string, donnees: unknown) {
    for (const f of this.ecouteurs[type] ?? []) f(new MessageEvent(type, { data: JSON.stringify(donnees) }));
  }
  close() {
    this.ferme = true;
  }
}


afterEach(() => vi.unstubAllGlobals());

const reponse = (statut: number, corps: unknown) =>
  Promise.resolve(new Response(JSON.stringify(corps), { status: statut }));

describe("useFluxDemande", () => {
  it("charge la vue, suit les événements et ferme au verdict", async () => {
    vi.stubGlobal("fetch", vi.fn(() => reponse(200, VUE)));
    let flux!: FauxFlux;
    const { result } = renderHook(() =>
      useFluxDemande("KAL-26-0101", (url) => (flux = new FauxFlux(url)) as unknown as EventSource),
    );
    await waitFor(() => expect(result.current.vue?.etape).toBe(1));
    expect(flux.url).toBe("/assure/demandes/KAL-26-0101/flux");
    act(() => flux.emettre("message", { auteur: "agent", texte: "Bonjour", actions: [] }));
    expect(result.current.messages).toHaveLength(1);
    act(() => flux.emettre("etape", { ...VUE, etape: 2, branche: null }));
    expect(result.current.vue?.etape).toBe(2);
    act(() => flux.emettre("verdict", { ...VUE, etape: 5 }));
    expect(flux.ferme).toBe(true);
  });

  it("signale la coupure et l'erreur d'accès", async () => {
    vi.stubGlobal("fetch", vi.fn(() => reponse(401, { detail: "session requise" })));
    let flux!: FauxFlux;
    const { result } = renderHook(() =>
      useFluxDemande("KAL-26-0101", (url) => (flux = new FauxFlux(url)) as unknown as EventSource),
    );
    await waitFor(() => expect(result.current.erreur).toBe(401));
    act(() => flux.onerror?.());
    expect(result.current.horsLigne).toBe(true);
    act(() => flux.onopen?.());
    expect(result.current.horsLigne).toBe(false);
  });
});

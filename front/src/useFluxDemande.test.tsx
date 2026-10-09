import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VUE } from "./test/donnees";
import { useFluxDemande } from "./useFluxDemande";

class FauxFlux {
  ecouteurs: Record<string, ((e: MessageEvent) => void)[]> = {};
  ferme = false;
  readyState = 1;
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

  describe("reprise après erreur HTTP", () => {
    const monter = () => {
      const flux: FauxFlux[] = [];
      const rendu = renderHook(() =>
        useFluxDemande("KAL-26-0101", (url) => {
          flux.push(new FauxFlux(url));
          return flux[flux.length - 1] as unknown as EventSource;
        }),
      );
      return { flux, ...rendu };
    };
    afterEach(() => vi.useRealTimers());

    it("401 sur le flux fermé : erreur 401, aucune réouverture", async () => {
      vi.useFakeTimers();
      vi.stubGlobal("fetch", vi.fn(() => reponse(200, VUE)));
      const { flux, result } = monter();
      await act(() => vi.advanceTimersByTimeAsync(0));
      vi.stubGlobal("fetch", vi.fn(() => reponse(401, { detail: "session requise" })));
      flux[0].readyState = 2;
      await act(async () => flux[0].onerror?.());
      await act(() => vi.advanceTimersByTimeAsync(10_000));
      expect(result.current.erreur).toBe(401);
      expect(result.current.horsLigne).toBe(true);
      expect(flux).toHaveLength(1);
    });

    it("flux fermé mais API joignable : rouvre après le délai en repartant de zéro", async () => {
      vi.useFakeTimers();
      vi.stubGlobal("fetch", vi.fn(() => reponse(200, VUE)));
      const { flux, result } = monter();
      await act(() => vi.advanceTimersByTimeAsync(0));
      act(() => flux[0].emettre("message", { auteur: "agent", texte: "Bonjour", actions: [] }));
      expect(result.current.messages).toHaveLength(1);
      flux[0].readyState = 2;
      await act(async () => flux[0].onerror?.());
      expect(flux).toHaveLength(1);
      await act(() => vi.advanceTimersByTimeAsync(3000));
      expect(flux).toHaveLength(2);
      expect(flux[1].url).toBe("/assure/demandes/KAL-26-0101/flux");
      expect(result.current.messages).toHaveLength(0);
    });

    it("le démontage ferme le flux et annule la réouverture programmée", async () => {
      vi.useFakeTimers();
      vi.stubGlobal("fetch", vi.fn(() => reponse(200, VUE)));
      const { flux, unmount } = monter();
      await act(() => vi.advanceTimersByTimeAsync(0));
      flux[0].readyState = 2;
      await act(async () => flux[0].onerror?.());
      unmount();
      expect(flux[0].ferme).toBe(true);
      await vi.advanceTimersByTimeAsync(10_000);
      expect(flux).toHaveLength(1);
    });
  });
});

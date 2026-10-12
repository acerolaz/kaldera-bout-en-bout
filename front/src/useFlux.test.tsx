import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EvenementVue } from "./api";
import { FauxEventSource, simulerFlux } from "./test/flux";
import { useFlux } from "./useFlux";

type Donnees = { etat: string | null };
const CLE = ["sonde"] as const; // stable : le flux n'est pas rouvert à chaque rendu
const maj = (_d: Donnees, e: EvenementVue): Donnees => ({ etat: e.etat });

function Sonde({ chemin }: { chemin: string | null }) {
  // abonnée au cache : un setQueryData du hook la fait se redessiner
  const { data } = useQuery({ queryKey: CLE, queryFn: async (): Promise<Donnees> => ({ etat: null }), staleTime: Infinity });
  const coupe = useFlux<Donnees>(chemin, CLE, maj);
  return <p>{coupe ? "coupé" : "ok"} · {data?.etat ?? "∅"}</p>;
}

const monter = (chemin: string | null) => {
  const client = new QueryClient();
  client.setQueryData(CLE, { etat: null });
  const invalider = vi.spyOn(client, "invalidateQueries");
  const rendu = render(<QueryClientProvider client={client}><Sonde chemin={chemin} /></QueryClientProvider>);
  return { client, invalider, rendu };
};

beforeEach(simulerFlux);
afterEach(() => vi.unstubAllGlobals());

const base = { reference: "KAL-26-0104", statut: "en_cours" as const, avancement_agent: 33 };

describe("useFlux", () => {
  it("ouvre /api + chemin ; relit à l'ouverture et à chaque fin d'étape", () => {
    const { invalider } = monter("/flux/demandes/KAL-26-0104");
    const source = FauxEventSource.instances[0];
    expect(source.url).toBe("/api/flux/demandes/KAL-26-0104");
    source.ouvrir();
    expect(invalider).toHaveBeenCalledTimes(1);
    source.emettre({ ...base, type: "etape_fin", etat: "pieces", statut: null, avancement_agent: 100 });
    expect(invalider).toHaveBeenCalledTimes(2);
  });

  it("sous-étape : applique les valeurs du serveur au cache", async () => {
    monter("/flux/demandes/KAL-26-0104");
    FauxEventSource.instances[0].emettre({ ...base, type: "sous_etape", etat: "pieces" });
    expect(await screen.findByText("ok · pieces")) // notification TanStack asynchrone
.toBeInTheDocument();
  });

  it("coupure : signalée jusqu'à la reconnexion", () => {
    monter("/flux/demandes/KAL-26-0104");
    const source = FauxEventSource.instances[0];
    source.couper();
    expect(screen.getByText(/^coupé/)).toBeInTheDocument();
    source.ouvrir();
    expect(screen.getByText(/^ok/)).toBeInTheDocument();
  });

  it("réponse non 200 (flux fermé par le navigateur) : rouvert après 3 s, badge levé à l'ouverture", () => {
    vi.useFakeTimers();
    try {
      const { invalider } = monter("/flux/demandes/KAL-26-0104");
      FauxEventSource.instances[0].couperDefinitivement();
      expect(screen.getByText(/^coupé/)).toBeInTheDocument();
      expect(FauxEventSource.instances).toHaveLength(1);
      act(() => void vi.advanceTimersByTime(3000));
      expect(FauxEventSource.instances).toHaveLength(2);
      FauxEventSource.instances[1].ouvrir();
      expect(screen.getByText(/^ok/)).toBeInTheDocument();
      expect(invalider).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("coupure réseau (le navigateur retente seul) : pas de seconde source", () => {
    vi.useFakeTimers();
    try {
      monter("/flux/demandes/KAL-26-0104");
      FauxEventSource.instances[0].couper();
      act(() => void vi.advanceTimersByTime(10000));
      expect(FauxEventSource.instances).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("sans chemin : aucun flux ; démontage : flux fermé", () => {
    monter(null);
    expect(FauxEventSource.instances).toHaveLength(0);
    const { rendu } = monter("/flux/lots/7");
    rendu.unmount();
    expect(FauxEventSource.instances[0].ferme).toBe(true);
  });
});

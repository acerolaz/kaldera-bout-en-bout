import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { EvenementVue } from "./api";

/**
 * Flux SSE (spec C3-3 §4.4). À l'ouverture (et à chaque reconnexion) puis à chaque fin d'étape ou de
 * dossier : relecture de l'état complet (GET, projection serveur). Début et sous-étapes : `maj` pose
 * les valeurs reçues dans le cache. `chemin` nul : aucun flux (dossier ou lot terminé).
 * `cle` et `maj` doivent être stables (useMemo, fonction de module). Renvoie vrai si le flux est coupé.
 */
export function useFlux<T>(chemin: string | null, cle: readonly unknown[], maj: (donnees: T, evenement: EvenementVue) => T): boolean {
  const client = useQueryClient();
  const [coupe, setCoupe] = useState(false);
  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- remise à zéro quand `chemin` change
    setCoupe(false);
    if (!chemin) return;
    const relire = () => void client.invalidateQueries({ queryKey: cle });
    let source: EventSource;
    let minuterie: ReturnType<typeof setTimeout> | undefined;
    const ouvrir = () => {
      source = new EventSource(`/api${chemin}`);
      source.onopen = () => {
        setCoupe(false);
        relire();
      };
      // coupure réseau : le navigateur se reconnecte seul (CONNECTING) ; réponse non 200 (502 du proxy
      // pendant que l'API est arrêtée, 503) : il abandonne (CLOSED) et c'est à nous de rouvrir
      source.onerror = () => {
        setCoupe(true);
        if (source.readyState === EventSource.CLOSED) minuterie = setTimeout(ouvrir, 3000);
      };
      source.addEventListener("avancement", (message) => {
        const evenement = JSON.parse((message as MessageEvent<string>).data) as EvenementVue;
        if (evenement.type === "etape_fin" || evenement.type === "dossier_fin") relire();
        else client.setQueryData<T>(cle, (donnees) => (donnees === undefined ? donnees : maj(donnees, evenement)));
      });
    };
    ouvrir();
    return () => {
      clearTimeout(minuterie);
      source.close();
    };
  }, [chemin, cle, maj, client]);
  return chemin !== null && coupe;
}

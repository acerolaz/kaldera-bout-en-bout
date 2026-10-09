import { useEffect, useRef, useState } from "react";
import { api, ErreurApi, type MessageChat, type VueDemande } from "./api";

type Ouvrir = (url: string) => EventSource;
const parDefaut: Ouvrir = (url) => new EventSource(url);

const DELAI_REOUVERTURE_MS = 3000;
const FERME = 2; // EventSource.CLOSED : le navigateur ne retente plus (réponse HTTP non 200)

/** Vue projetée + messages du chat ; le flux SSE reprend seul (Last-Event-ID) et se ferme au verdict. */
export function useFluxDemande(reference: string, ouvrir: Ouvrir = parDefaut) {
  const [vue, setVue] = useState<VueDemande | null>(null);
  const [messages, setMessages] = useState<MessageChat[]>([]);
  const [horsLigne, setHorsLigne] = useState(false);
  const [erreur, setErreur] = useState<number | null>(null);
  // `ouvrir` passe par une ref : un appelant qui fournit une fonction littérale ne relance pas l'effet à chaque rendu.
  const ouvrirRef = useRef(ouvrir);
  useEffect(() => {
    ouvrirRef.current = ouvrir;
  });

  useEffect(() => {
    let actif = true;
    let termine = false;
    let flux: EventSource | null = null;
    let minuteur: ReturnType<typeof setTimeout> | undefined;
    let relecture: ReturnType<typeof setTimeout> | undefined;
    setMessages([]);
    // 401/404 sont définitifs (la page redirige ou dit « introuvable ») ; toute autre panne (503, réseau)
    // affiche « hors ligne » et la vue est relue après un délai, que le flux soit ouvert ou non.
    const charger = () =>
      api
        .demande(reference)
        .then((v) => {
          if (!actif) return;
          setVue(v);
          setHorsLigne(false);
        })
        .catch((e: unknown) => {
          if (!actif) return;
          if (e instanceof ErreurApi && (e.statut === 401 || e.statut === 404)) return setErreur(e.statut);
          setHorsLigne(true);
          clearTimeout(relecture);
          relecture = setTimeout(charger, DELAI_REOUVERTURE_MS);
        });
    charger();

    const surVue = (e: MessageEvent) => {
      setHorsLigne(false);
      setVue(JSON.parse(e.data) as VueDemande);
    };

    // Flux fermé par une réponse HTTP d'erreur : on sonde l'API pour distinguer session perdue / dossier
    // disparu (on s'arrête, la page redirige) d'une panne passagère (on rouvre après un délai).
    const surErreur = (courant: EventSource) => {
      setHorsLigne(true);
      if (courant.readyState !== FERME || termine) return;
      api
        .demande(reference)
        .then((v) => {
          if (actif) setVue(v);
        })
        .catch((e: unknown) => {
          if (e instanceof ErreurApi && (e.statut === 401 || e.statut === 404)) {
            if (actif) setErreur(e.statut);
            return "arret" as const;
          }
        })
        .then((arret) => {
          if (!actif || termine || arret === "arret") return;
          clearTimeout(minuteur); // deux erreurs rapprochées : une seule réouverture
          minuteur = setTimeout(() => {
            // Une réouverture manuelle perd Last-Event-ID : le serveur rejoue depuis 0, d'où la remise à zéro.
            setMessages([]);
            ouvrirFlux();
          }, DELAI_REOUVERTURE_MS);
        });
    };

    function ouvrirFlux() {
      const courant = ouvrirRef.current(`/assure/demandes/${encodeURIComponent(reference)}/flux`);
      flux = courant;
      courant.addEventListener("etape", surVue as EventListener);
      courant.addEventListener("piece", surVue as EventListener);
      courant.addEventListener("verdict", ((e: MessageEvent) => {
        termine = true;
        surVue(e);
        courant.close();
      }) as EventListener);
      courant.addEventListener("message", ((e: MessageEvent) => {
        setMessages((liste) => [...liste, JSON.parse(e.data) as MessageChat]);
      }) as EventListener);
      courant.onerror = () => surErreur(courant);
      courant.onopen = () => setHorsLigne(false);
    }

    ouvrirFlux();
    return () => {
      actif = false;
      clearTimeout(minuteur);
      clearTimeout(relecture);
      flux?.close();
    };
  }, [reference]);

  return { vue, setVue, messages, horsLigne, erreur };
}

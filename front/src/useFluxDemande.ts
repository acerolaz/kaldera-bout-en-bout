import { useEffect, useRef, useState } from "react";
import { api, ErreurApi, type MessageChat, type VueDemande } from "./api";

type Ouvrir = (url: string) => EventSource;
const parDefaut: Ouvrir = (url) => new EventSource(url);

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
    setMessages([]);
    api
      .demande(reference)
      .then((v) => actif && setVue(v))
      .catch((e: unknown) => actif && setErreur(e instanceof ErreurApi ? e.statut : 0));
    const flux = ouvrirRef.current(`/assure/demandes/${encodeURIComponent(reference)}/flux`);
    const surVue = (e: MessageEvent) => {
      setHorsLigne(false);
      setVue(JSON.parse(e.data) as VueDemande);
    };
    flux.addEventListener("etape", surVue as EventListener);
    flux.addEventListener("piece", surVue as EventListener);
    flux.addEventListener("verdict", ((e: MessageEvent) => {
      surVue(e);
      flux.close();
    }) as EventListener);
    flux.addEventListener("message", ((e: MessageEvent) => {
      setMessages((liste) => [...liste, JSON.parse(e.data) as MessageChat]);
    }) as EventListener);
    flux.onerror = () => setHorsLigne(true);
    flux.onopen = () => setHorsLigne(false);
    return () => {
      actif = false;
      flux.close();
    };
  }, [reference]);

  return { vue, setVue, messages, horsLigne, erreur };
}

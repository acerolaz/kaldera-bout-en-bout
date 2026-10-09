import { useEffect, useRef, useState, type ReactNode } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import type { TypePiece } from "../api";
import { BandeauStatut } from "../components/BandeauStatut";
import { Depot, type DepotHandle } from "../components/Depot";
import { ListePieces } from "../components/ListePieces";
import { Soumettre } from "../components/Soumettre";
import { Stepper } from "../components/Stepper";
import { VerdictCarte } from "../components/VerdictCarte";
import { T } from "../textes";
import { useFluxDemande } from "../useFluxDemande";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface Props {
  reference: string;
  /** Emplacement du chat (Task 10) : reçoit les messages et l'accès à la zone de dépôt. */
  chat?: (args: { messages: ReturnType<typeof useFluxDemande>["messages"]; deposer?: () => void }) => ReactNode;
}

export function Sinistre({ reference, chat }: Props) {
  const { vue, setVue, messages, horsLigne, erreur } = useFluxDemande(reference);
  const naviguer = useNavigate();
  const expire = () => naviguer("/connexion", { replace: true });
  const depot = useRef<DepotHandle>(null);
  const [type, setType] = useState<TypePiece>("facture");
  useEffect(() => {
    const aFournir = vue?.pieces.find((p) => p.statut === "a_fournir" || p.statut === "a_refaire");
    if (aFournir) setType(aFournir.type);
  }, [vue?.reference]); // eslint-disable-line react-hooks/exhaustive-deps — type initial seulement
  if (erreur === 401) return <Navigate to="/connexion" replace />;
  if (erreur !== null) return <main className="p-4"><p>{T.introuvable}</p></main>;
  if (!vue) {
    return (
      <main className="mx-auto max-w-[1200px] p-4">
        {horsLigne ? (
          <Alert><AlertDescription>{T.horsLigne}</AlertDescription></Alert>
        ) : (
          <p role="status">{T.chargement}</p>
        )}
      </main>
    );
  }
  const peutDeposer = !vue.soumise && vue.etape === 1; // sinon la zone de dépôt n'est pas affichée
  const deposer = (t?: TypePiece) => {
    if (t) setType(t);
    depot.current?.focus();
  };

  return (
    <div className="min-h-screen">
      <header className="bg-primary text-primary-foreground">
        <div className="mx-auto flex max-w-[1200px] items-center gap-3 p-4">
          <span className="font-semibold text-or-sur-primaire">{T.appli}</span>
          <h1 className="text-lg font-semibold">{T.sinistres.dossier(vue.reference)}</h1>
        </div>
      </header>
      {horsLigne && (
        <Alert className="mx-auto mt-4 max-w-[1200px]"><AlertDescription>{T.horsLigne}</AlertDescription></Alert>
      )}
      {/* Mobile : une colonne, ordre statut, pièces, dépôt, stepper, verdict (order-*) ; les colonnes
          sont `contents`. À partir de lg, elles deviennent deux piles indépendantes (pas de lignes communes). */}
      <main className="mx-auto flex max-w-[1200px] flex-col gap-4 p-4 lg:grid lg:grid-cols-[320px_1fr] lg:items-start">
        <div className="contents lg:flex lg:flex-col lg:gap-4">
          <div className="order-4 lg:order-1"><Stepper vue={vue} /></div>
          <div className="order-2 lg:order-2">
            <ListePieces pieces={vue.pieces} onDeposer={peutDeposer ? deposer : undefined} />
          </div>
        </div>
        <div className="contents lg:flex lg:flex-col lg:gap-4">
          <div className="order-1 lg:order-1"><BandeauStatut vue={vue} /></div>
          {peutDeposer && (
            <div className="order-3 space-y-3 lg:order-2">
              <Depot ref={depot} reference={reference} type={type} onTypeChange={setType} onDepose={() => undefined} onExpire={expire} />
              <Soumettre vue={vue} onSoumise={setVue} onExpire={expire} />
            </div>
          )}
          {vue.verdict && (
            <div className="order-5 lg:order-3"><VerdictCarte verdict={vue.verdict} /></div>
          )}
        </div>
      </main>
      {/* Le chat s'arrête au verdict : le serveur refuse alors tout message (409 dossier_clos). */}
      {!vue.verdict && chat?.({ messages, deposer: peutDeposer ? () => deposer() : undefined })}
    </div>
  );
}

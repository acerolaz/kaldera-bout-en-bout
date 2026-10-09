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
  chat?: (args: { messages: ReturnType<typeof useFluxDemande>["messages"]; deposer: () => void }) => ReactNode;
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
  if (!vue) return null;
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
      <main className="mx-auto grid max-w-[1200px] gap-4 p-4 lg:grid-cols-[320px_1fr]">
        <div className="order-1 lg:col-start-2 lg:row-start-1"><BandeauStatut vue={vue} /></div>
        <div className="order-2 lg:col-start-1 lg:row-start-2"><ListePieces pieces={vue.pieces} onDeposer={deposer} /></div>
        {!vue.soumise && vue.etape === 1 && (
          <div className="order-3 space-y-3 lg:col-start-2 lg:row-start-2">
            <Depot ref={depot} reference={reference} type={type} onTypeChange={setType} onDepose={() => undefined} onExpire={expire} />
            <Soumettre vue={vue} onSoumise={setVue} onExpire={expire} />
          </div>
        )}
        <div className="order-4 lg:col-start-1 lg:row-start-1"><Stepper vue={vue} /></div>
        {vue.verdict && (
          <div className="order-5 lg:col-start-2 lg:row-start-3"><VerdictCarte verdict={vue.verdict} /></div>
        )}
      </main>
      {chat?.({ messages, deposer: () => deposer() })}
    </div>
  );
}

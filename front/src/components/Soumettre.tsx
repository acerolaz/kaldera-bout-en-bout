import { useState } from "react";
import { ErreurApi, api, type VueDemande } from "../api";
import { T } from "../textes";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

interface Props {
  vue: VueDemande;
  onSoumise: (v: VueDemande) => void;
  /** Appelé sur 401 (session expirée) : la page renvoie à la connexion. */
  onExpire?: () => void;
}

export function Soumettre({ vue, onSoumise, onExpire }: Props) {
  const [confirmation, setConfirmation] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [dejaSoumise, setDejaSoumise] = useState(false);
  const enAnalyse = vue.pieces.some((p) => p.statut === "en_analyse");
  const incomplet = vue.pieces.some((p) => p.statut !== "validee");
  if (vue.soumise || dejaSoumise) return <p role="status" className="font-medium">{T.soumettre.soumis}</p>;

  const envoyer = async (confirmer: boolean) => {
    setErreur(null);
    try {
      onSoumise(await api.soumettre(vue.reference, confirmer));
    } catch (e) {
      if (!(e instanceof ErreurApi)) return setErreur(T.depot.erreurs.defaut); // réseau coupé : on le dit, on ne jette pas
      if (e.statut === 401) return onExpire?.();
      if (e.detail === "deja_soumise") return setDejaSoumise(true); // double clic : le dossier est déjà soumis, rien à dire
      if (e.detail === "confirmation_requise") setConfirmation(true);
      else setErreur(e.detail === "analyse_en_cours" ? T.soumettre.analyse : T.depot.erreurs.defaut);
    }
  };

  return (
    <div className="space-y-2">
      <Button className="min-h-11 w-full" disabled={enAnalyse} onClick={() => (incomplet ? setConfirmation(true) : envoyer(false))}>
        {T.soumettre.bouton}
      </Button>
      {enAnalyse && <p className="text-sm text-muted-foreground">{T.soumettre.analyse}</p>}
      {erreur && <p role="alert" className="text-sm font-medium text-destructive">{erreur}</p>}
      <AlertDialog open={confirmation} onOpenChange={setConfirmation}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{T.soumettre.confirmerTitre}</AlertDialogTitle>
            <AlertDialogDescription>{T.soumettre.confirmerTexte}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="min-h-11">{T.soumettre.annuler}</AlertDialogCancel>
            <AlertDialogAction className="min-h-11" onClick={() => envoyer(true)}>{T.soumettre.confirmer}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

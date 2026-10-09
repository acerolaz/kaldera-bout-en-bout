import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ErreurApi, api, type ResumeDemande } from "../api";
import { T } from "../textes";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export function MesSinistres() {
  const [demandes, setDemandes] = useState<ResumeDemande[] | null>(null);
  const [indisponible, setIndisponible] = useState(false);
  const naviguer = useNavigate();
  const charger = useCallback(() => {
    api
      .demandes()
      .then((d) => {
        setDemandes(d);
        setIndisponible(false);
      })
      .catch((e) => {
        if (e instanceof ErreurApi && e.statut === 401) naviguer("/connexion");
        else setIndisponible(true); // 503 ou réseau : on le dit, l'assuré réessaie
      });
  }, [naviguer]);
  useEffect(charger, [charger]);
  const deconnecter = async () => {
    await api.deconnecter().catch((e: unknown) => {
      if (!(e instanceof ErreurApi)) throw e; // session déjà expirée ou serveur muet : on quitte quand même
    });
    naviguer("/connexion");
  };
  return (
    <main className="mx-auto max-w-2xl p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{T.sinistres.titre}</h1>
        <Button variant="outline" className="min-h-11" onClick={deconnecter}>{T.sinistres.deconnexion}</Button>
      </div>
      {indisponible && (
        <Alert className="mb-4">
          <AlertDescription>
            {T.indisponible}
            <Button variant="outline" className="mt-2 min-h-11" onClick={charger}>{T.reessayer}</Button>
          </AlertDescription>
        </Alert>
      )}
      {demandes?.length === 0 && <p>{T.sinistres.vide}</p>}
      <ul className="space-y-2">
        {demandes?.map((d) => (
          <li key={d.reference}>
            <Link to={`/sinistres/${d.reference}`} className="block min-h-11 rounded-md border bg-card p-3 hover:bg-muted">
              <span className="font-medium">{T.sinistres.dossier(d.reference)}</span>
              <span className="block text-sm text-muted-foreground">
                {d.branche ? T.branches[d.branche] : T.etapes[d.etape - 1]}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}

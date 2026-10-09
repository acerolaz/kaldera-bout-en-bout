import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ErreurApi, api, type ResumeDemande } from "../api";
import { T } from "../textes";
import { Button } from "@/components/ui/button";

export function MesSinistres() {
  const [demandes, setDemandes] = useState<ResumeDemande[] | null>(null);
  const naviguer = useNavigate();
  useEffect(() => {
    api.demandes().then(setDemandes).catch((e) => {
      if (e instanceof ErreurApi && e.statut === 401) naviguer("/connexion");
    });
  }, [naviguer]);
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

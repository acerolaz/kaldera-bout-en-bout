import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErreurApi, lire, type EvenementVue, type LigneLot, type LotVue } from "@/api";
import { Barre } from "@/components/Barre";
import { Statut } from "@/components/Statut";
import { Button } from "@/components/ui/button";
import { ABSENT, duree, nomComplet } from "@/format";
import { ETAPES } from "@/statuts";
import { useFlux } from "@/useFlux";
import { Cadre, Vide } from "./socle";

/** Début d'étape et sous-étapes : seule la ligne du dossier concerné change (barres indépendantes). */
const majLot = (lot: LotVue, e: EvenementVue): LotVue => ({
  ...lot,
  dossiers: lot.dossiers.map((d) =>
    d.reference === e.reference ? { ...d, statut: e.statut ?? d.statut, etape_en_cours: e.etat ?? d.etape_en_cours } : d,
  ),
});

export function Lot() {
  const { id = "" } = useParams();
  const zone = useRef<HTMLDivElement>(null);
  const cle = useMemo(() => ["lot", id], [id]);
  const requete = useQuery({ queryKey: cle, queryFn: () => lire<LotVue>(`/lots/${encodeURIComponent(id)}`) });
  const enDirect = requete.data !== undefined && requete.data.avancement < 100;
  const coupe = useFlux(enDirect ? `/flux/lots/${encodeURIComponent(id)}` : null, cle, majLot);

  let contenu: ReactNode;
  if (requete.isPending) {
    contenu = (
      <div>
        <p role="status" className="sr-only">Chargement du lot…</p>
        <div aria-busy="true" className="h-40 animate-pulse rounded-lg bg-muted" />
      </div>
    );
  } else if (!requete.data && requete.error instanceof ErreurApi && [404, 422].includes(requete.error.statut)) {
    contenu = (
      <Vide>
        Lot introuvable.{" "}
        <Link to="/" className="font-medium text-primary underline underline-offset-4">Retour à la liste des demandes</Link>
      </Vide>
    );
  } else if (!requete.data) {
    contenu = (
      <div role="alert" className="flex items-center gap-3 rounded-lg border border-ton-danger p-4">
        <p>Impossible de charger le lot : {requete.error?.message}</p>
        <Button variant="outline" onClick={() => {
          zone.current?.focus();
          void requete.refetch();
        }}>Réessayer</Button>
      </div>
    );
  } else {
    contenu = <Suivi lot={requete.data} coupe={coupe} />;
  }
  return (
    <Cadre titre={`Lot ${id}`}>
      <div ref={zone} tabIndex={-1} data-testid="lot" className="flex flex-col gap-3 outline-none">{contenu}</div>
    </Cadre>
  );
}

function Suivi({ lot, coupe }: { lot: LotVue; coupe: boolean }) {
  const c = lot.compteurs;
  const escalades = Object.entries(c.escalade).map(([file, n]) => `${file} ${n}`).join(" · ") || "0";
  const lignes: [string, ReactNode][] = [
    ["Acceptées", c.acceptee],
    ["Refusées", c.refusee],
    ["Escaladées", escalades],
    ["Modes dégradés", c.mode_degrade],
    ["Durée écoulée", <Ecoule key="ecoule" debut={lot.debut} fin={lot.fin} />],
  ];
  return (
    <>
      <section aria-label="En-tête du lot" className="flex flex-col gap-3 rounded-lg border bg-card p-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Barre valeur={lot.avancement} libelle="Avancement du lot" />
          <span className="tabular-nums">{lot.avancement} %</span>
          <span>{lot.dossiers.length} dossiers</span>
          {coupe ? <span className="font-medium text-ton-attention">Reconnexion…</span> : null}
        </div>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm sm:grid-cols-[repeat(5,max-content_auto)]">
          {lignes.map(([cle, valeur]) => (
            <div key={cle} className="contents">
              <dt className="text-muted-foreground">{cle}</dt>
              <dd className="tabular-nums">{valeur}</dd>
            </div>
          ))}
        </dl>
      </section>
      <div className="overflow-auto rounded-lg border">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">Dossiers du lot</caption>
          <thead className="sticky top-0 bg-card text-left">
            <tr className="border-b">
              {["Référence", "Assuré", "Police", "Avancement", "Étape en cours", "Durée", "Issue", "Badges"].map((titre) => (
                <th key={titre} scope="col" className="px-3 py-2 font-medium">{titre}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lot.dossiers.map((d) => <LigneDossier key={d.reference} dossier={d} />)}
          </tbody>
        </table>
      </div>
    </>
  );
}

function LigneDossier({ dossier: d }: { dossier: LigneLot }) {
  return (
    <tr className="h-10 border-b last:border-0">
      <td className="px-3 font-mono">
        <Link to={`/demandes/${encodeURIComponent(d.reference)}`} className="text-primary underline-offset-4 hover:underline">
          {d.reference}
        </Link>
      </td>
      <td className="px-3">{nomComplet(d.nom, d.prenom)}</td>
      <td className="px-3 font-mono">{d.police ?? ABSENT}</td>
      <td className="px-3">
        <div className="flex items-center gap-2">
          <Barre valeur={d.avancement} libelle={`Avancement de ${d.reference}`} className="w-24" />
          <span className="tabular-nums">{d.avancement} %</span>
        </div>
      </td>
      <td className="px-3">{d.etape_en_cours ? (ETAPES[d.etape_en_cours] ?? d.etape_en_cours) : ABSENT}</td>
      <td className="px-3 tabular-nums">{duree(d.duree_ms / 1000)}</td>
      <td className="px-3">{d.issue ? <Statut code={d.issue} /> : <Statut code={d.statut} />}</td>
      <td className="px-3">
        <div className="flex flex-wrap gap-2">
          {d.mode_degrade ? <Statut code="mode_degrade" /> : null}
          {d.borne ? <Statut code="borne" /> : null}
        </div>
      </td>
    </tr>
  );
}

function Ecoule({ debut, fin }: { debut: string; fin: string | null }) {
  const [maintenant, setMaintenant] = useState(() => Date.now());
  useEffect(() => {
    if (fin) return;
    const minuterie = setInterval(() => setMaintenant(Date.now()), 1000);
    return () => clearInterval(minuterie);
  }, [fin]);
  return <>{duree(((fin ? Date.parse(fin) : maintenant) - Date.parse(debut)) / 1000)}</>;
}

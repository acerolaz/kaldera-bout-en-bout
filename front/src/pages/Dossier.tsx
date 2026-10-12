import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { type ReactNode, useMemo, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { ErreurApi, lire, type CarteAntifraude, type DossierVue, type Etape, type EvenementVue } from "@/api";
import { Barre } from "@/components/Barre";
import { Statut } from "@/components/Statut";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ABSENT, euros, nomComplet } from "@/format";
import { ETAPES } from "@/statuts";
import { useFlux } from "@/useFlux";
import { Cadre, Vide } from "./socle";

const AVIS: Record<CarteAntifraude["statut"], string> = { ok: "Avis obtenu", indisponible: "Indisponible", non_requis: "Non requis" };

const secondes = (ms: number) => `${(ms / 1000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} s`;
const dureeEtape = (ms: number) => (ms < 1000 ? `${Math.round(ms)} ms` : secondes(ms)); // une étape rapide ne lit pas « 0 s »
const montant = (valeur: number | null) => (valeur === null ? ABSENT : euros(valeur));

/** Début d'étape et sous-étapes : statut et % agent reçus du serveur, posés sur la carte concernée. */
const majDossier = (d: DossierVue, e: EvenementVue): DossierVue => ({
  ...d,
  etapes: d.etapes.map((x) =>
    x.etat === e.etat ? { ...x, statut: e.statut ?? x.statut, avancement: e.avancement_agent ?? x.avancement } : x,
  ),
});

export function Dossier() {
  const { reference = "" } = useParams();
  const zone = useRef<HTMLDivElement>(null);
  const cle = useMemo(() => ["dossier", reference], [reference]);
  const requete = useQuery({
    queryKey: cle,
    queryFn: () => lire<DossierVue>(`/demandes/${encodeURIComponent(reference)}`),
  });
  const enDirect = requete.data !== undefined && requete.data.avancement < 100;
  const coupe = useFlux(enDirect ? `/flux/demandes/${encodeURIComponent(reference)}` : null, cle, majDossier);

  let contenu: ReactNode;
  if (requete.isPending) {
    contenu = (
      <div>
        <p role="status" className="sr-only">Chargement du dossier…</p>
        <div aria-busy="true" className="h-40 animate-pulse rounded-lg bg-muted" />
      </div>
    );
  } else if (!requete.data && requete.isError && requete.error instanceof ErreurApi && requete.error.statut === 404) {
    contenu = (
      <Vide>
        Dossier introuvable.{" "}
        <Link to="/" className="font-medium text-primary underline underline-offset-4">Retour à la liste des demandes</Link>
      </Vide>
    );
  } else if (!requete.data && requete.isError) {
    contenu = (
      <div role="alert" className="flex items-center gap-3 rounded-lg border border-ton-danger p-4">
        <p>Impossible de charger le dossier : {requete.error.message}</p>
        <Button variant="outline" onClick={() => {
          zone.current?.focus(); // le bouton disparaît au clic : le focus reste dans la page
          void requete.refetch();
        }}>Réessayer</Button>
      </div>
    );
  } else {
    contenu = <Detail dossier={requete.data} coupe={coupe} />;
  }
  return (
    <Cadre titre={`Dossier ${reference}`}>
      <div ref={zone} tabIndex={-1} data-testid="dossier" className="flex flex-col gap-3 outline-none">
        {contenu}
      </div>
    </Cadre>
  );
}

function Detail({ dossier: d, coupe }: { dossier: DossierVue; coupe: boolean }) {
  const enCours = d.etapes.find((e) => e.statut === "en_cours");
  return (
    <>
      <section aria-label="En-tête du dossier" className="flex flex-col gap-3 rounded-lg border bg-card p-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <p className="text-lg font-semibold">{nomComplet(d.nom, d.prenom)}</p>
          <p>Police <span className="font-mono">{d.police ?? ABSENT}</span></p>
          <p>Formule {d.formule ?? ABSENT}</p>
          <Statut code={d.statut} />
          {d.issue ? <Statut code={d.issue} /> : null}
          {d.mode_degrade ? <Statut code="mode_degrade" /> : null}
          <Garanties dossier={d} />
        </div>
        {d.issue ? (
          <p className="text-sm">
            {d.file ? <>File <strong>{d.file}</strong> · </> : null}
            {d.motif ?? ABSENT}
            {d.montant_rembourse !== null ? <> · Remboursé <span className="tabular-nums">{euros(d.montant_rembourse)}</span></> : null}
          </p>
        ) : null}
        <div className="flex items-center gap-3 text-sm">
          <Barre valeur={d.avancement} libelle="Avancement du dossier" />
          <span className="tabular-nums">{d.avancement} %</span>
          <span className="tabular-nums">{`${secondes(d.duree_ms)} / ${secondes(d.budget_ms)}`}</span>
        </div>
      </section>

      {d.arret ? (
        <div className="flex items-center gap-2 rounded-lg border border-ton-danger p-3 text-sm">
          <Statut code="borne" />
          <span>{d.arret.borne} = {d.arret.valeur.toLocaleString("fr-FR")}{d.arret.etat ? ` (étape ${ETAPES[d.arret.etat] ?? d.arret.etat})` : ""}</span>
        </div>
      ) : null}

      <p aria-live="polite" className="text-sm text-muted-foreground">
        {enCours ? `Étape en cours : ${ETAPES[enCours.etat] ?? enCours.etat}` : d.avancement === 100 ? "Traitement terminé" : null}
        {coupe ? <span className="ml-3 font-medium text-ton-attention">Reconnexion…</span> : null}
      </p>

      <ol aria-label="Étapes du traitement" className="flex flex-col gap-2">
        {d.etapes.map((etape) => (
          <CarteEtape key={etape.etat} etape={etape} antifraude={etape.etat === "antifraude" ? d.antifraude : null} />
        ))}
      </ol>
    </>
  );
}

function CarteEtape({ etape: e, antifraude }: { etape: Etape; antifraude: CarteAntifraude | null }) {
  const execution = [
    e.duree_ms !== null && e.statut !== "sautee" ? dureeEtape(e.duree_ms) : null,
    e.mode ? `${e.mode}${e.cause ? ` (${e.cause})` : ""}` : null,
    e.modele,
    e.tours_llm !== null ? `${e.tours_llm} tour${e.tours_llm > 1 ? "s" : ""}` : null,
    e.jetons !== null ? `${e.jetons} jetons` : null,
    e.passages > 1 ? `${e.passages} passages` : null,
  ].filter(Boolean);
  return (
    <li className="flex flex-col gap-2 rounded-lg border bg-card p-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-medium">{ETAPES[e.etat] ?? e.etat}</h2>
        <Statut code={e.statut} />
        {execution.length > 0 ? <span className="text-sm text-muted-foreground tabular-nums">{execution.join(" · ")}</span> : null}
      </div>
      {e.statut === "en_cours" ? (
        <div className="flex items-center gap-2 text-sm">
          <Barre valeur={e.avancement} libelle={`Avancement de l'étape ${ETAPES[e.etat] ?? e.etat}`} className="w-32" />
          <span className="tabular-nums">{e.avancement} %</span>
        </div>
      ) : null}
      {e.resume ? <p className="text-sm">{e.resume}</p> : null}
      {e.de && e.vers ? (
        <p className="text-xs text-muted-foreground">
          {e.de} → {e.vers}{e.garde ? ` (garde ${e.garde})` : ""}
        </p>
      ) : null}
      {antifraude ? <DetailAntifraude carte={antifraude} /> : null}
    </li>
  );
}

function DetailAntifraude({ carte: c }: { carte: CarteAntifraude }) {
  const lignes: [string, string][] = [
    ["Requis", c.requis ? "oui" : "non"],
    ["Indicateurs", c.indicateurs.length ? c.indicateurs.join(", ") : "aucun"],
    ["Statut", AVIS[c.statut]],
    ["Niveau", c.niveau ?? ABSENT],
    ["Score", c.score === null ? ABSENT : c.score.toLocaleString("fr-FR")],
    ["Évaluation", c.evaluation_id ?? ABSENT],
    ["Modèle", c.version_modele ?? ABSENT],
  ];
  if (c.note) lignes.push(["Note", c.note]);
  if (c.cause) lignes.push(["Motif du mode dégradé", c.cause]);
  return (
    <section aria-label="Carte anti-fraude" className="rounded-md border p-2 text-sm">
      <Definitions lignes={lignes} className="gap-y-1" />
    </section>
  );
}

function Garanties({ dossier: d }: { dossier: DossierVue }) {
  const g = d.garanties;
  const lignes: [string, string][] = [
    ["Formule", g.formule ?? ABSENT],
    ["Franchise", montant(g.franchise)],
    ["Plafond", montant(g.plafond)],
    ["Souscription", g.date_souscription ?? ABSENT],
    ["Statut du contrat", g.statut_contrat ?? ABSENT],
    ["Cotisations à jour", g.cotisations_a_jour === null ? ABSENT : g.cotisations_a_jour ? "oui" : "non"],
    ["Extraction", `${g.statut_extraction} (${g.source})`],
    ["Modèle", g.modele ?? ABSENT],
    ["Empreinte", g.sha256 ? g.sha256.slice(0, 12) : ABSENT],
  ];
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" className="ml-auto">
          <ShieldCheck aria-hidden="true" />
          Garanties
        </Button>
      </SheetTrigger>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Garanties</SheetTitle>
          <SheetDescription>Extraites du contrat, en lecture seule.</SheetDescription>
        </SheetHeader>
        <Definitions lignes={lignes} className="gap-y-2 px-4 text-sm" ddClassName="tabular-nums" />
      </SheetContent>
    </Sheet>
  );
}

function Definitions({ lignes, className, ddClassName }: { lignes: [string, string][]; className: string; ddClassName?: string }) {
  return (
    <dl className={`grid grid-cols-[max-content_1fr] gap-x-4 ${className}`}>
      {lignes.map(([cle, valeur]) => (
        <div key={cle} className="contents">
          <dt className="text-muted-foreground">{cle}</dt>
          <dd className={ddClassName}>{valeur}</dd>
        </div>
      ))}
    </dl>
  );
}

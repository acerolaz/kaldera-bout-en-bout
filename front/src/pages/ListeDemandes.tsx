import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { envoyer, ErreurApi, lire, type LigneDemande, type LotLance } from "@/api";
import { Statut } from "@/components/Statut";
import { Button } from "@/components/ui/button";
import { ABSENT, euros, nomComplet } from "@/format";
import { STATUTS } from "@/statuts";
import { Cadre, Vide } from "./socle";

const FILTRES = ["statut", "issue", "file", "mode_degrade", "q"] as const;
const STATUTS_DEMANDE = ["admission", "prete", "en_cours", "terminee", "secours"];
const ISSUES = ["acceptee", "refusee", "escalade"];

const libelle = (code: string) => (Object.hasOwn(STATUTS, code) ? STATUTS[code].libelle : code);
const texte = (valeur: string | null) => valeur ?? ABSENT;
const messageLancement = (erreur: Error) =>
  erreur instanceof ErreurApi && erreur.references.length > 0 ? `${erreur.message} : ${erreur.references.join(", ")}` : erreur.message;

export function ListeDemandes() {
  const [params, setParams] = useSearchParams();
  const filtres = new URLSearchParams();
  for (const cle of FILTRES) {
    const valeur = params.get(cle);
    if (valeur) filtres.set(cle, valeur);
  }
  const requete = filtres.toString();
  const toutes = useQuery({ queryKey: ["demandes", ""], queryFn: () => lire<LigneDemande[]>("/demandes") });
  const liste = useQuery({
    queryKey: ["demandes", requete],
    queryFn: () => lire<LigneDemande[]>(requete ? `/demandes?${requete}` : "/demandes"),
  });
  // sélection rattachée aux filtres : en changer la vide, sans effet ni état dupliqué
  const [choix, setChoix] = useState<{ requete: string; refs: Set<string> }>({ requete, refs: new Set() });
  // sélection effective : bornée aux dossiers actuellement lançables (un 409 puis refetch les retire)
  const lancables = new Set((liste.data ?? []).filter((l) => l.selectionnable).map((l) => l.reference));
  const selection = new Set([...(choix.requete === requete ? choix.refs : [])].filter((r) => lancables.has(r)));
  const selectionner = (refs: Set<string>) => {
    lancer.reset();
    setChoix({ requete, refs });
  };
  const navigate = useNavigate();
  const client = useQueryClient();
  const lancer = useMutation({
    mutationFn: (references: string[]) => envoyer<LotLance>("/traitements", { references }),
    onSuccess: (lot) =>
      navigate(lot.references.length === 1 ? `/demandes/${encodeURIComponent(lot.references[0])}` : `/lots/${lot.lot_id}`),
    onError: () => void client.invalidateQueries({ queryKey: ["demandes"] }),
  });
  const q = params.get("q") ?? "";
  const champ = useRef<HTMLInputElement>(null);
  const zone = useRef<HTMLDivElement>(null);
  // champ non contrôlé : sa valeur suit l'URL (effacement, retour arrière) sans le remonter
  useEffect(() => {
    if (champ.current) champ.current.value = q;
  }, [q]);
  const fileActive = params.get("file");
  const files = [
    ...new Set([...(toutes.data ?? []).flatMap((l) => (l.file ? [l.file] : [])), ...(fileActive ? [fileActive] : [])]),
  ].sort();

  const changer = (cle: (typeof FILTRES)[number], valeur: string) => {
    const valeurs = new Map(filtres);
    if (valeur) valeurs.set(cle, valeur);
    else valeurs.delete(cle);
    // ordre canonique : une même combinaison de filtres donne toujours la même URL
    setParams(FILTRES.flatMap((c): [string, string][] => (valeurs.has(c) ? [[c, valeurs.get(c)!]] : [])));
  };
  const rechercher = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    changer("q", String(new FormData(e.currentTarget).get("q") ?? "").trim());
  };

  return (
    <Cadre titre="Liste des demandes">
      <form role="search" aria-label="Filtres des demandes" onSubmit={rechercher} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Recherche
          <input
            ref={champ}
            name="q"
            type="search"
            defaultValue={q}
            placeholder="Référence, nom, police"
            className="h-9 rounded-md border bg-card px-2"
          />
        </label>
        <Choix
          nom="Statut"
          tous="Tous"
          valeur={params.get("statut")}
          options={STATUTS_DEMANDE.map((c) => [c, libelle(c)])}
          onChange={(v) => changer("statut", v)}
        />
        <Choix
          nom="Issue"
          tous="Toutes"
          valeur={params.get("issue")}
          options={ISSUES.map((c) => [c, libelle(c)])}
          onChange={(v) => changer("issue", v)}
        />
        <Choix
          nom="File"
          tous="Toutes"
          valeur={params.get("file")}
          options={files.map((f) => [f, f])}
          onChange={(v) => changer("file", v)}
        />
        <label className="flex h-9 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={params.get("mode_degrade") === "true"}
            onChange={(e) => changer("mode_degrade", e.target.checked ? "true" : "")}
          />
          Mode dégradé seulement
        </label>
        <Button type="submit" variant="outline">Rechercher</Button>
      </form>

      <div
        ref={zone}
        tabIndex={-1}
        data-testid="liste"
        className="outline-none"
      >
        {liste.isPending ? (
          <div className="flex flex-col gap-1">
            <p role="status" className="sr-only">Chargement des demandes…</p>
            <div aria-busy="true" className="flex flex-col gap-1">
              {Array.from({ length: 5 }, (_, i) => (
                <div key={i} className="h-10 animate-pulse rounded-md bg-muted" />
              ))}
            </div>
          </div>
        ) : liste.isError ? (
          <div role="alert" className="flex items-center gap-3 rounded-lg border border-ton-danger p-4">
            <p>Impossible de charger les demandes : {liste.error.message}</p>
            <Button variant="outline" onClick={() => {
                zone.current?.focus();
                void liste.refetch();
              }}>Réessayer</Button>
          </div>
        ) : liste.data.length === 0 ? (
          requete ? (
            <Vide>
              Aucune demande ne correspond aux filtres.{" "}
              <Button variant="link" onClick={() => {
                  zone.current?.focus();
                  setParams(new URLSearchParams());
                }}>Effacer les filtres</Button>
            </Vide>
          ) : (
            <Vide>Aucune demande en base : lancer <code>make demo</code> puis <code>make scenarios</code>.</Vide>
          )
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <Button disabled={selection.size === 0 || lancer.isPending} onClick={() => lancer.mutate([...selection])}>
                <Play aria-hidden="true" />
                Traiter la sélection ({selection.size})
              </Button>
              {lancer.isError ? (
                <p role="alert" className="text-sm text-ton-danger">
                  Impossible de lancer le traitement : {messageLancement(lancer.error)}
                </p>
              ) : null}
            </div>
            <Tableau lignes={liste.data} selection={selection} selectionner={selectionner} />
          </div>
        )}
      </div>
    </Cadre>
  );
}

function Choix({ nom, tous, valeur, options, onChange }: {
  nom: string;
  tous: string;
  valeur: string | null;
  options: [string, string][];
  onChange: (valeur: string) => void;
}) {
  // libellé relié par htmlFor (et non englobant) : son nom accessible ne contient pas le texte des options
  const id = useId();
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={id}>{nom}</label>
      <select id={id} value={valeur ?? ""} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-md border bg-card px-2">
        <option value="">{tous}</option>
        {options.map(([code, texteOption]) => (
          <option key={code} value={code}>{texteOption}</option>
        ))}
      </select>
    </div>
  );
}

function Tableau({ lignes, selection, selectionner }: {
  lignes: LigneDemande[];
  selection: Set<string>;
  selectionner: (refs: Set<string>) => void;
}) {
  const possibles = lignes.filter((l) => l.selectionnable).map((l) => l.reference);
  const tout = possibles.length > 0 && possibles.every((r) => selection.has(r));
  const basculer = (reference: string) => {
    const refs = new Set(selection);
    if (refs.has(reference)) refs.delete(reference);
    else refs.add(reference);
    selectionner(refs);
  };
  return (
    <div className="max-h-[70vh] overflow-auto rounded-lg border">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">Demandes de remboursement</caption>
        <thead className="sticky top-0 bg-card text-left">
          <tr className="border-b">
            <th scope="col" className="w-10 px-3 py-2">
              <input
                type="checkbox"
                aria-label="Tout sélectionner"
                checked={tout}
                disabled={possibles.length === 0}
                onChange={() => selectionner(tout ? new Set() : new Set(possibles))}
                className="size-4"
              />
            </th>
            {["Référence", "Assuré", "Police", "Sinistre", "Montant déclaré", "Statut", "Issue", "File", "Mode"].map((titre) => (
              <th key={titre} scope="col" className="px-3 py-2 font-medium">{titre}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lignes.map((l) => (
            <tr key={l.reference} className="h-10 border-b last:border-0">
              <td className="px-3">
                <input
                  type="checkbox"
                  aria-label={`Sélectionner ${l.reference}`}
                  checked={selection.has(l.reference)}
                  disabled={!l.selectionnable}
                  title={l.motif_non_selectionnable ?? undefined}
                  aria-describedby={l.motif_non_selectionnable ? `motif-${l.reference}` : undefined}
                  onChange={() => basculer(l.reference)}
                  className="size-4"
                />
                {l.motif_non_selectionnable ? (
                  <span id={`motif-${l.reference}`} className="sr-only">{l.motif_non_selectionnable}</span>
                ) : null}
              </td>
              <td className="px-3 font-mono">
                <Link to={`/demandes/${encodeURIComponent(l.reference)}`} className="text-primary underline-offset-4 hover:underline">
                  {l.reference}
                </Link>
              </td>
              <td className="px-3">{nomComplet(l.nom, l.prenom)}</td>
              <td className="px-3 font-mono">{texte(l.police)}</td>
              <td className="px-3">{l.type_sinistre ? l.type_sinistre.replaceAll("_", " ") : ABSENT}</td>
              <td className="px-3 text-right tabular-nums">{l.montant_declare === null ? ABSENT : euros(l.montant_declare)}</td>
              <td className="px-3"><Statut code={l.statut} /></td>
              <td className="px-3">{l.issue ? <Statut code={l.issue} /> : ABSENT}</td>
              <td className="px-3">{texte(l.file)}</td>
              <td className="px-3">{l.mode_degrade ? <Statut code="mode_degrade" /> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

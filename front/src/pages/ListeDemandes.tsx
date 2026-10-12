import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useId, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { lire, type LigneDemande } from "@/api";
import { Statut } from "@/components/Statut";
import { Button } from "@/components/ui/button";
import { ABSENT, euros, nomComplet } from "@/format";
import { STATUTS } from "@/statuts";
import { Cadre, Vide } from "./socle";

const FILTRES = ["statut", "issue", "file", "mode_degrade", "q"] as const;
const STATUTS_DEMANDE = ["admission", "en_cours", "terminee", "secours"];
const ISSUES = ["acceptee", "refusee", "escalade"];

const libelle = (code: string) => (Object.hasOwn(STATUTS, code) ? STATUTS[code].libelle : code);
const texte = (valeur: string | null) => valeur ?? ABSENT;

export function ListeDemandes() {
  const [params, setParams] = useSearchParams();
  const filtres = new URLSearchParams();
  for (const cle of FILTRES) {
    const valeur = params.get(cle);
    if (valeur) filtres.set(cle, valeur);
  }
  const requete = filtres.toString();
  const q = params.get("q") ?? "";
  const champ = useRef<HTMLInputElement>(null);
  const zone = useRef<HTMLDivElement>(null);
  // champ non contrôlé : sa valeur suit l'URL (effacement, retour arrière) sans le remonter
  useEffect(() => {
    if (champ.current) champ.current.value = q;
  }, [q]);
  const toutes = useQuery({ queryKey: ["demandes", ""], queryFn: () => lire<LigneDemande[]>("/demandes") });
  const liste = useQuery({
    queryKey: ["demandes", requete],
    queryFn: () => lire<LigneDemande[]>(requete ? `/demandes?${requete}` : "/demandes"),
  });
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
          <Tableau lignes={liste.data} />
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

function Tableau({ lignes }: { lignes: LigneDemande[] }) {
  return (
    <div className="max-h-[70vh] overflow-auto rounded-lg border">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">Demandes de remboursement</caption>
        <thead className="sticky top-0 bg-card text-left">
          <tr className="border-b">
            {["Référence", "Assuré", "Police", "Sinistre", "Montant déclaré", "Statut", "Issue", "File", "Mode"].map((titre) => (
              <th key={titre} scope="col" className="px-3 py-2 font-medium">{titre}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lignes.map((l) => (
            <tr key={l.reference} className="h-10 border-b last:border-0">
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

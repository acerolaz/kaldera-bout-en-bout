// Miroir TypeScript des schémas de src/kaldera/vue_gestionnaire.py (spec C3-2 §2) : l'IHM affiche, n'interprète rien.

export type StatutEtape = "en_attente" | "termine" | "sautee" | "echec" | "repli" | "degrade";
export type CodeIssue = "acceptee" | "refusee" | "escalade";

export type LigneDemande = {
  reference: string;
  nom: string | null;
  prenom: string | null;
  police: string | null;
  type_sinistre: string | null;
  montant_declare: number | null;
  statut: string;
  issue: CodeIssue | null;
  file: string | null;
  mode_degrade: boolean;
};

export type Garanties = {
  formule: string | null;
  franchise: number | null;
  plafond: number | null;
  date_souscription: string | null;
  statut_contrat: string | null;
  cotisations_a_jour: boolean | null;
  statut_extraction: string;
  source: string;
  modele: string | null;
  sha256: string | null;
};

export type Etape = {
  etat: string;
  statut: StatutEtape;
  avancement: number;
  passages: number;
  duree_ms: number | null;
  latence_llm_ms: number | null;
  modele: string | null;
  mode: "llm" | "repli" | null;
  cause: string | null;
  tours_llm: number | null;
  jetons: number | null;
  sortie_rejetee: boolean;
  de: string | null;
  vers: string | null;
  garde: string | null;
  resume: string;
};

export type CarteAntifraude = {
  requis: boolean;
  indicateurs: string[];
  statut: "ok" | "indisponible" | "non_requis";
  niveau: string | null;
  score: number | null;
  evaluation_id: string | null;
  version_modele: string | null;
  note: string | null;
  cause: string | null;
};

export type ArretVue = { borne: string; valeur: number; etat: string | null };

export type DossierVue = {
  reference: string;
  statut: string;
  fiche: Record<string, unknown> | null;
  nom: string | null;
  prenom: string | null;
  police: string | null;
  formule: string | null;
  avancement: number;
  duree_ms: number;
  budget_ms: number;
  issue: CodeIssue | null;
  file: string | null;
  motif: string | null;
  mode_degrade: boolean;
  montant_rembourse: number | null;
  garanties: Garanties;
  etapes: Etape[];
  antifraude: CarteAntifraude | null;
  arret: ArretVue | null;
};

export class ErreurApi extends Error {
  statut: number;
  constructor(statut: number, message: string) {
    super(message);
    this.name = "ErreurApi";
    this.statut = statut;
  }
}

/** GET sur l'API (proxy Vite /api) ; une réponse non 2xx lève ErreurApi(statut, detail). */
export async function lire<T>(chemin: string): Promise<T> {
  const reponse = await fetch(`/api${chemin}`);
  if (!reponse.ok) {
    const corps = (await reponse.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof corps?.detail === "string" ? corps.detail : `Erreur ${reponse.status}`;
    throw new ErreurApi(reponse.status, detail);
  }
  return (await reponse.json()) as T;
}

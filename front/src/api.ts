// Miroir TypeScript des schémas de src/kaldera/vue_gestionnaire.py (spec C3-2 §2) : l'IHM affiche, n'interprète rien.

export type StatutEtape = "en_attente" | "en_cours" | "termine" | "sautee" | "echec" | "repli" | "degrade";
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
  selectionnable: boolean;
  motif_non_selectionnable: string | null;
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

export type LigneLot = {
  reference: string;
  nom: string | null;
  prenom: string | null;
  police: string | null;
  statut: string;
  avancement: number;
  etape_en_cours: string | null;
  duree_ms: number;
  issue: CodeIssue | null;
  file: string | null;
  mode_degrade: boolean;
  borne: string | null;
};

export type CompteursLot = { acceptee: number; refusee: number; escalade: Record<string, number>; mode_degrade: number };

export type LotVue = {
  id: number;
  debut: string;
  fin: string | null;
  avancement: number;
  compteurs: CompteursLot;
  dossiers: LigneLot[];
};

export type LotLance = { lot_id: number; references: string[] };

/** Événement SSE (spec C3-3 §3.4) : valeurs calculées par le serveur, affichées telles quelles. */
export type EvenementVue = {
  type: "etape_debut" | "sous_etape" | "etape_fin" | "dossier_fin";
  reference: string;
  etat: string | null;
  statut: "en_cours" | null;
  avancement_agent: number | null;
};

export class ErreurApi extends Error {
  statut: number;
  references: string[];
  constructor(statut: number, message: string, references: string[] = []) {
    super(message);
    this.name = "ErreurApi";
    this.statut = statut;
    this.references = references;
  }
}

async function decoder<T>(reponse: Response): Promise<T> {
  if (!reponse.ok) {
    const corps = (await reponse.json().catch(() => null)) as { detail?: unknown; references?: unknown } | null;
    const detail = typeof corps?.detail === "string" ? corps.detail : `Erreur ${reponse.status}`;
    const references = Array.isArray(corps?.references) ? corps.references.map(String) : [];
    throw new ErreurApi(reponse.status, detail, references);
  }
  return (await reponse.json()) as T;
}

/** GET sur l'API (proxy Vite /api) ; une réponse non 2xx lève ErreurApi(statut, detail). */
export async function lire<T>(chemin: string): Promise<T> {
  return decoder<T>(await fetch(`/api${chemin}`));
}

/** POST JSON sur l'API ; 404 / 409 portent les références refusées (ErreurApi.references). */
export async function envoyer<T>(chemin: string, corps: unknown): Promise<T> {
  return decoder<T>(
    await fetch(`/api${chemin}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corps),
    }),
  );
}

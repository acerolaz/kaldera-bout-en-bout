import type { DossierVue, Etape, LigneDemande, LotVue } from "@/api";

export const LIGNES: LigneDemande[] = [
  {
    reference: "KAL-26-0203", nom: "Durand", prenom: "Paul", police: "CTR-778803",
    type_sinistre: "degat_des_eaux", montant_declare: 9200, statut: "terminee", issue: "escalade",
    file: "cellule_fraude", mode_degrade: true, selectionnable: false, motif_non_selectionnable: "Déjà traité",
  },
  {
    reference: "KAL-26-0103", nom: "Martin", prenom: "Léa", police: "CTR-778802",
    type_sinistre: "vol", montant_declare: 640, statut: "terminee", issue: "refusee",
    file: null, mode_degrade: false, selectionnable: false, motif_non_selectionnable: "Déjà traité",
  },
  {
    reference: "KAL-26-0101", nom: "Martin", prenom: "Claire", police: "CTR-778801",
    type_sinistre: "degat_des_eaux", montant_declare: null, statut: "admission", issue: null,
    file: null, mode_degrade: false, selectionnable: false, motif_non_selectionnable: "Pièces en cours d'analyse",
  },
  {
    reference: "KAL-26-0105", nom: "Petit", prenom: "Jean", police: "CTR-778805",
    type_sinistre: "degat_des_eaux", montant_declare: 4200, statut: "prete", issue: null,
    file: null, mode_degrade: false, selectionnable: true, motif_non_selectionnable: null,
  },
  {
    reference: "KAL-26-0104", nom: "Roux", prenom: "Anne", police: "CTR-778804",
    type_sinistre: "incendie", montant_declare: 1500, statut: "prete", issue: null,
    file: null, mode_degrade: false, selectionnable: true, motif_non_selectionnable: null,
  },
];

const etape = (etat: string, champs: Partial<Etape> = {}): Etape => ({
  etat, statut: "termine", avancement: 100, passages: 1, duree_ms: 12.5, latence_llm_ms: null,
  modele: null, mode: null, cause: null, tours_llm: null, jetons: null, sortie_rejetee: false,
  de: etat, vers: null, garde: "ok", resume: "", ...champs,
});

export const DOSSIER_ACCEPTE: DossierVue = {
  reference: "KAL-26-0101", statut: "terminee", fiche: null, nom: "Martin", prenom: "Claire",
  police: "CTR-778801", formule: "confort", avancement: 100, duree_ms: 2400, budget_ms: 8000,
  issue: "acceptee", file: null, motif: "Dossier conforme", mode_degrade: false,
  montant_rembourse: 1230,
  garanties: {
    formule: "confort", franchise: 150, plafond: 8000, date_souscription: "2024-01-15",
    statut_contrat: "actif", cotisations_a_jour: true, statut_extraction: "valide",
    source: "extraction_vlm", modele: "fake-vlm", sha256: "9f2c4e1ab3d5",
  },
  etapes: [
    etape("eligibilite", { vers: "pieces", resume: "Éligible" }),
    etape("pieces", { vers: "estimation", mode: "llm", modele: "gpt-test", tours_llm: 2, jetons: 340, resume: "Pièces complètes (3 retenues)" }),
    etape("estimation", { vers: "antifraude", mode: "llm", modele: "gpt-test", tours_llm: 1, jetons: 210, resume: "Estimé 1 230 € = min(déclaré 1 850 €, justifié 1 380 €) − franchise 150 €, plafond 8 000 € non atteint" }),
    etape("antifraude", { vers: "decision", resume: "Avis non requis" }),
    etape("decision", { vers: "acceptee", mode: "llm", modele: "gpt-test", tours_llm: 1, jetons: 180, resume: "Acceptée : 1 230 €" }),
  ],
  antifraude: {
    requis: false, indicateurs: [], statut: "non_requis", niveau: null, score: null,
    evaluation_id: null, version_modele: null, note: null, cause: null,
  },
  arret: null,
};

export const DOSSIER_DEGRADE: DossierVue = {
  ...DOSSIER_ACCEPTE,
  reference: "KAL-26-0203", nom: "Durand", prenom: "Paul", police: "CTR-778803",
  issue: "escalade", file: "cellule_fraude", motif: "Avis anti-fraude indisponible",
  mode_degrade: true, montant_rembourse: null, avancement: 100, // terminal ⇒ 100
  etapes: [
    etape("eligibilite", { vers: "pieces", resume: "Éligible" }),
    etape("pieces", { vers: "estimation", resume: "Pièces complètes (2 retenues)" }),
    etape("estimation", { statut: "repli", mode: "repli", cause: "disjoncteur", vers: "antifraude", resume: "Estimé 8 000 €" }),
    etape("antifraude", { statut: "degrade", vers: "decision", resume: "Avis indisponible : transport:timeout" }),
    etape("decision", { statut: "en_attente", avancement: 0, passages: 0, duree_ms: null, de: null, garde: null }),
  ],
  antifraude: {
    requis: true, indicateurs: ["F2", "F4"], statut: "indisponible", niveau: null, score: null,
    evaluation_id: null, version_modele: null, note: null, cause: "transport:timeout",
  },
  arret: { borne: "duree_max_s", valeur: 8, etat: "decision" },
};

export const DOSSIER_EN_COURS: DossierVue = {
  ...DOSSIER_ACCEPTE,
  statut: "en_cours", avancement: 20, issue: null, motif: null, montant_rembourse: null,
  etapes: [
    etape("eligibilite", { vers: "pieces", resume: "Éligible" }),
    etape("pieces", { statut: "en_cours", avancement: 0, duree_ms: null, de: null, garde: null }),
    ...["estimation", "antifraude", "decision"].map((e) =>
      etape(e, { statut: "en_attente", avancement: 0, passages: 0, duree_ms: null, de: null, garde: null })),
  ],
};

export const LOT: LotVue = {
  id: 7, debut: "2026-10-12T09:00:00Z", fin: null, avancement: 50,
  compteurs: { acceptee: 1, refusee: 0, escalade: { cellule_fraude: 1 }, mode_degrade: 1 },
  dossiers: [
    { reference: "KAL-26-0104", nom: "Roux", prenom: "Anne", police: "CTR-778804", statut: "terminee", avancement: 100,
      etape_en_cours: null, duree_ms: 2400, issue: "acceptee", file: null, mode_degrade: false, borne: null },
    { reference: "KAL-26-0105", nom: "Petit", prenom: "Jean", police: "CTR-778805", statut: "en_cours", avancement: 40,
      etape_en_cours: "estimation", duree_ms: 900, issue: null, file: null, mode_degrade: false, borne: null },
    { reference: "KAL-26-0106", nom: "Blanc", prenom: "Lou", police: "CTR-778806", statut: "terminee", avancement: 100,
      etape_en_cours: null, duree_ms: 8100, issue: "escalade", file: "cellule_fraude", mode_degrade: true, borne: "duree_max_s" },
    { reference: "KAL-26-0107", nom: "Noir", prenom: "Max", police: "CTR-778807", statut: "en_cours", avancement: 0,
      etape_en_cours: "eligibilite", duree_ms: 0, issue: null, file: null, mode_degrade: false, borne: null },
  ],
};

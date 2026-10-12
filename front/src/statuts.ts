import {
  CircleCheck, CirclePlay, CircleX, Clock, FileSearch, LifeBuoy, Loader, OctagonX, RotateCcw, SkipForward, UserRound,
  type LucideIcon,
} from "lucide-react";

export type Ton = "neutre" | "info" | "succes" | "attention" | "danger";
export type DefinitionStatut = { libelle: string; icone: LucideIcon; ton: Ton };

/** Codes du back-end (demandes.statut, Issue, étapes de la machine) ; spec C3-1 §3.4. */
export const STATUTS: Record<string, DefinitionStatut> = {
  // demande
  admission: { libelle: "En analyse", icone: FileSearch, ton: "info" },
  prete: { libelle: "Prête", icone: CirclePlay, ton: "info" },
  en_cours: { libelle: "En traitement", icone: Loader, ton: "info" },
  terminee: { libelle: "Terminée", icone: CircleCheck, ton: "succes" },
  secours: { libelle: "Fiche de secours", icone: LifeBuoy, ton: "attention" },
  // issue
  acceptee: { libelle: "Acceptée", icone: CircleCheck, ton: "succes" },
  refusee: { libelle: "Refusée", icone: CircleX, ton: "danger" },
  escalade: { libelle: "Escaladée", icone: UserRound, ton: "attention" },
  // étape (en_cours : même code que la demande)
  en_attente: { libelle: "En attente", icone: Clock, ton: "neutre" },
  termine: { libelle: "Terminée", icone: CircleCheck, ton: "succes" },
  sautee: { libelle: "Sautée", icone: SkipForward, ton: "neutre" },
  echec: { libelle: "Échec", icone: CircleX, ton: "danger" },
  repli: { libelle: "Repli déterministe", icone: RotateCcw, ton: "attention" },
  degrade: { libelle: "Mode dégradé", icone: LifeBuoy, ton: "attention" },
  // badges
  mode_degrade: { libelle: "Mode dégradé", icone: LifeBuoy, ton: "attention" },
  borne: { libelle: "Borne atteinte", icone: OctagonX, ton: "danger" },
};

/** Libellés des étapes de la machine (E2, E3). */
export const ETAPES: Record<string, string> = {
  eligibilite: "Éligibilité", pieces: "Pièces", estimation: "Estimation", antifraude: "Anti-fraude", decision: "Décision",
};

export type TypePiece = "facture" | "photo" | "depot_plainte";
export type StatutPiece = "a_fournir" | "en_analyse" | "validee" | "a_refaire";
export type Branche = "attente_pieces" | "gestionnaire";

export interface PieceAttendue { type: TypePiece; libelle: string; statut: StatutPiece; raison: string | null }
export interface Verdict {
  issue: "acceptee" | "partielle" | "refusee" | "transmise";
  montant: number | null;
  franchise: number | null;
  explication: string;
  pieces_retenues: string[];
}
export interface VueDemande {
  reference: string;
  cree_le: string;
  etape: number;
  branche: Branche | null;
  horodatages: Record<string, string>;
  restant_estime_s: number;
  pieces: PieceAttendue[];
  soumise: boolean;
  verdict: Verdict | null;
}
export interface ResumeDemande { reference: string; cree_le: string; etape: number; branche: Branche | null }
export interface MessageChat { auteur: "assure" | "agent"; texte: string; actions: "deposer"[] }
export interface Recu { statut: "recu" | "deja_recu"; avertissement_multipage: boolean }

export class ErreurApi extends Error {
  constructor(public statut: number, public detail: string) {
    super(detail);
  }
}

async function appel<T>(chemin: string, init?: RequestInit): Promise<T> {
  const reponse = await fetch(chemin, { credentials: "same-origin", ...init });
  if (!reponse.ok) {
    let detail = reponse.statusText;
    try {
      detail = String((await reponse.json()).detail ?? detail);
    } catch {
      /* corps non JSON : statusText suffit */
    }
    throw new ErreurApi(reponse.status, detail);
  }
  return (reponse.status === 204 ? undefined : await reponse.json()) as T;
}

const json = (corps: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(corps),
});
const url = (reference: string) => `/assure/demandes/${encodeURIComponent(reference)}`;

export const api = {
  connecter: (identifiant: string, mot_de_passe: string) =>
    appel<void>("/assure/session", json({ identifiant, mot_de_passe })),
  deconnecter: () => appel<void>("/assure/session", { method: "DELETE" }),
  demandes: () => appel<ResumeDemande[]>("/assure/demandes"),
  demande: (reference: string) => appel<VueDemande>(url(reference)),
  deposer: (reference: string, type: TypePiece, fichier: File) => {
    const corps = new FormData();
    corps.append("type", type);
    corps.append("fichier", fichier);
    return appel<Recu>(`${url(reference)}/pieces`, { method: "POST", body: corps });
  },
  soumettre: (reference: string, confirmer: boolean) =>
    appel<VueDemande>(`${url(reference)}/soumettre`, json({ confirmer })),
  envoyer: (reference: string, texte: string) =>
    appel<MessageChat>(`${url(reference)}/messages`, json({ texte })),
};

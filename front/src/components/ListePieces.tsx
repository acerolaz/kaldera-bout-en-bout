import { AlertTriangle, CheckCircle2, Circle, Clock } from "lucide-react";
import type { PieceAttendue, StatutPiece, TypePiece } from "../api";
import { T } from "../textes";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const ICONES: Record<StatutPiece, { Icone: typeof Circle; couleur: string }> = {
  a_fournir: { Icone: Circle, couleur: "text-foreground" },
  en_analyse: { Icone: Clock, couleur: "text-muted-foreground" },
  validee: { Icone: CheckCircle2, couleur: "text-succes" },
  a_refaire: { Icone: AlertTriangle, couleur: "text-a-refaire" },
};

export function ListePieces({ pieces, onDeposer }: { pieces: PieceAttendue[]; onDeposer?: (t: TypePiece) => void }) {
  return (
    <Card className="p-4">
      <h2 className="mb-3 text-lg font-semibold">{T.pieces.titre}</h2>
      <ul className="space-y-3">
        {pieces.map((p) => {
          const { Icone, couleur } = ICONES[p.statut];
          return (
            <li key={p.type} className="flex items-start justify-between gap-3">
              <div className="flex gap-2">
                <Icone aria-hidden="true" className={`mt-0.5 size-5 shrink-0 ${couleur}`} />
                <div>
                  <p className="font-medium">{p.libelle}</p>
                  <p className={`text-sm ${couleur}`}>{T.pieces.statuts[p.statut]}</p>
                  {p.raison && <p className="text-sm text-muted-foreground">{p.raison}</p>}
                </div>
              </div>
              {onDeposer && (p.statut === "a_fournir" || p.statut === "a_refaire") && (
                <Button variant="outline" className="min-h-11" aria-label={`${T.pieces.deposer} : ${p.libelle}`} onClick={() => onDeposer(p.type)}>
                  {T.pieces.deposer}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

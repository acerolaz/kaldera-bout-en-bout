import { Circle } from "lucide-react";
import { cn } from "@/lib/utils";
import { STATUTS, type Ton } from "@/statuts";

const COULEURS: Record<Ton, string> = {
  neutre: "text-ton-neutre",
  info: "text-ton-info",
  succes: "text-ton-succes",
  attention: "text-ton-attention",
  danger: "text-ton-danger",
};

/** Icône + libellé + couleur ; un code hors catalogue s'affiche brut, en neutre. */
export function Statut({ code }: { code: string }) {
  const definition = Object.hasOwn(STATUTS, code) ? STATUTS[code] : undefined;
  const Icone = definition?.icone ?? Circle;
  return (
    <span
      data-testid="statut"
      className={cn("inline-flex items-center gap-1 text-sm font-medium", COULEURS[definition?.ton ?? "neutre"])}
    >
      <Icone aria-hidden="true" className="size-4 shrink-0" />
      {definition?.libelle ?? code}
    </span>
  );
}

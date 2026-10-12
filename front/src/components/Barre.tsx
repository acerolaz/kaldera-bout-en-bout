import { cn } from "@/lib/utils";

/** Barre de progression accessible (role progressbar, nom, valeur) ; la valeur vient du serveur. */
export function Barre({ valeur, libelle, className }: { valeur: number; libelle: string; className?: string }) {
  return (
    <div
      role="progressbar"
      aria-label={libelle}
      aria-valuenow={valeur}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-2 w-48 overflow-hidden rounded-full bg-muted", className)}
    >
      <div className="h-full bg-primary transition-[width]" style={{ width: `${valeur}%` }} />
    </div>
  );
}

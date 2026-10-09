import { useEffect, useState } from "react";
import type { VueDemande } from "../api";
import { duree } from "../format";
import { T } from "../textes";
import { Card } from "@/components/ui/card";

export function BandeauStatut({ vue }: { vue: VueDemande }) {
  const [maintenant, setMaintenant] = useState(() => Date.now());
  const terminee = vue.verdict !== null;
  useEffect(() => {
    if (terminee) return;
    const id = setInterval(() => setMaintenant(Date.now()), 1000);
    return () => clearInterval(id);
  }, [terminee]);
  const libelle = vue.branche ? T.branches[vue.branche] : T.etapes[vue.etape - 1];
  const ecoule = (maintenant - new Date(vue.cree_le).getTime()) / 1000;
  const progression = vue.verdict ? 1 : (vue.etape - 1) / 4;
  const rayon = 28;
  const tour = 2 * Math.PI * rayon;
  return (
    <Card className="flex items-center gap-4 p-4">
      <svg viewBox="0 0 64 64" className="size-16 shrink-0" aria-hidden="true">
        <circle cx="32" cy="32" r={rayon} fill="none" strokeWidth="6" className="stroke-muted" />
        <circle
          cx="32" cy="32" r={rayon} fill="none" strokeWidth="6" strokeLinecap="round"
          className="stroke-primary transition-[stroke-dashoffset] duration-300 motion-reduce:transition-none"
          strokeDasharray={tour} strokeDashoffset={tour * (1 - progression)} transform="rotate(-90 32 32)"
        />
      </svg>
      <div>
        <p aria-live="polite" className="text-lg font-semibold">{libelle}</p>
        <p className="text-sm text-muted-foreground">
          {vue.verdict
            ? T.statut.termine
            : `${T.statut.ecoule(duree(ecoule))}${vue.restant_estime_s > 0 ? ` · ${T.statut.restant(duree(vue.restant_estime_s))}` : ""}`}
        </p>
      </div>
    </Card>
  );
}

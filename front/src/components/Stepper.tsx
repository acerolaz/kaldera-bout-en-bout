import { Check } from "lucide-react";
import type { VueDemande } from "../api";
import { heure } from "../format";
import { T } from "../textes";

const POSITION_BRANCHE = { attente_pieces: 1, gestionnaire: 5 } as const;

export function Stepper({ vue }: { vue: VueDemande }) {
  const finie = vue.verdict !== null;
  return (
    <nav aria-label={T.stepper.titre}>
      <h2 className="mb-3 text-lg font-semibold">{T.stepper.titre}</h2>
      <ol className="space-y-4">
        {T.etapes.map((libelle, i) => {
          const n = i + 1;
          const faite = n < vue.etape || (finie && n === vue.etape);
          const courante = n === vue.etape && !faite;
          const horodatage = vue.horodatages[String(n)];
          const branche = vue.branche && POSITION_BRANCHE[vue.branche] === n ? T.branches[vue.branche] : null;
          return (
            <li key={n} aria-current={courante ? "step" : undefined} className="flex gap-3">
              <span
                aria-hidden="true"
                className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border-2 text-xs ${
                  faite ? "border-succes bg-succes text-white" : courante ? "border-or font-semibold" : "border-muted-foreground"
                }`}
              >
                {faite ? <Check className="size-4" /> : n}
              </span>
              <div>
                <span className={courante ? "font-semibold" : ""}>{libelle}</span>
                {(faite || courante) && <span className="sr-only"> ({faite ? T.stepper.faite : T.stepper.courante})</span>}
                {horodatage && (
                  <time dateTime={horodatage} className="block text-sm text-muted-foreground">
                    {heure(horodatage)}
                  </time>
                )}
                {branche && <p className="mt-1 ms-2 border-s-2 border-or ps-2 text-sm font-medium">{branche}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

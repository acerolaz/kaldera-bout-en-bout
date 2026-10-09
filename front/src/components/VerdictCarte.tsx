import type { Verdict } from "../api";
import { euros } from "../format";
import { T } from "../textes";
import { Card } from "@/components/ui/card";

export function VerdictCarte({ verdict }: { verdict: Verdict }) {
  return (
    <Card className="p-4" aria-labelledby="titre-verdict">
      <h2 id="titre-verdict" className="text-lg font-semibold">{T.verdict.titre}</h2>
      <p className="mt-1 text-xl font-semibold text-primary">{T.verdict.issues[verdict.issue]}</p>
      {verdict.montant !== null && (
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-muted-foreground">{T.verdict.montant}</dt>
          <dd className="font-semibold">{euros(verdict.montant)}</dd>
          {verdict.franchise !== null && (
            <>
              <dt className="text-muted-foreground">{T.verdict.franchise}</dt>
              <dd>{euros(verdict.franchise)}</dd>
            </>
          )}
        </dl>
      )}
      <p className="mt-3">{verdict.explication}</p>
      {verdict.pieces_retenues.length > 0 && (
        <>
          <h3 className="mt-3 font-medium">{T.verdict.retenues}</h3>
          <ul className="list-disc ps-5">
            {verdict.pieces_retenues.map((p) => <li key={p}>{p}</li>)}
          </ul>
        </>
      )}
    </Card>
  );
}

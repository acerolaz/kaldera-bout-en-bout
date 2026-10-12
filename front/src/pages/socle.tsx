import { type ReactNode, useEffect } from "react";
import { Link, useParams } from "react-router-dom";

export function Cadre({ titre, children }: { titre: string; children: ReactNode }) {
  useEffect(() => {
    document.title = `Kaldera · ${titre}`;
  }, [titre]);
  return (
    <section className="flex flex-col gap-3">
      <h1 className="text-xl font-semibold">{titre}</h1>
      {children}
    </section>
  );
}

export const Vide = ({ children }: { children: ReactNode }) => (
  <p className="rounded-lg border border-dashed p-6 text-muted-foreground">{children}</p>
);

export function Lot() {
  const { id = "" } = useParams();
  return (
    <Cadre titre={`Lot ${id}`}>
      <Vide>Écran livré au sous-projet C3-3 : avancement de chaque dossier du lot.</Vide>
    </Cadre>
  );
}

export function Introuvable() {
  return (
    <Cadre titre="Page introuvable">
      <p>
        <Link to="/" className="font-medium text-primary underline underline-offset-4">
          Retour à la liste des demandes
        </Link>
      </p>
    </Cadre>
  );
}

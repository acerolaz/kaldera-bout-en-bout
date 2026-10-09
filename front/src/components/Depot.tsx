import { forwardRef, useEffect, useId, useImperativeHandle, useRef, useState } from "react";
import { ErreurApi, api, type Recu, type TypePiece } from "../api";
import { T } from "../textes";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export interface DepotHandle { focus: () => void }
interface Props {
  reference: string;
  type: TypePiece;
  onTypeChange: (t: TypePiece) => void;
  onDepose: (recu: Recu) => void;
  /** Appelé sur 401 (session expirée) : la page renvoie à la connexion. */
  onExpire?: () => void;
}

export const Depot = forwardRef<DepotHandle, Props>(function Depot({ reference, type, onTypeChange, onDepose, onExpire }, ref) {
  const [fichier, setFichier] = useState<File | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [multipage, setMultipage] = useState(false);
  const selectRef = useRef<HTMLSelectElement>(null);
  const idErreur = useId();
  useImperativeHandle(ref, () => ({ focus: () => selectRef.current?.focus() }));

  const choisir = (f: File | undefined) => {
    setFichier(f ?? null);
    setErreur(null);
    setInfo(null);
    setMultipage(false);
  };
  const envoyer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fichier) return;
    setEnvoi(true);
    try {
      const recu = await api.deposer(reference, type, fichier);
      setInfo(recu.statut === "recu" ? T.depot.recu : T.depot.dejaRecu);
      setMultipage(recu.avertissement_multipage);
      setFichier(null);
      onDepose(recu);
    } catch (err) {
      if (err instanceof ErreurApi && err.statut === 401) return onExpire?.();
      const statut = err instanceof ErreurApi ? String(err.statut) : "defaut";
      setErreur(T.depot.erreurs[statut] ?? T.depot.erreurs.defaut);
    } finally {
      setEnvoi(false);
    }
  };
  const [apercu, setApercu] = useState<string | null>(null);
  useEffect(() => {
    if (!fichier || !fichier.type.startsWith("image/")) return setApercu(null);
    const url = URL.createObjectURL(fichier);
    setApercu(url);
    return () => URL.revokeObjectURL(url);
  }, [fichier]);

  return (
    <Card className="p-4">
      <h2 className="mb-3 text-lg font-semibold">{T.depot.titre}</h2>
      <form onSubmit={envoyer} className="space-y-3">
        <div>
          <label htmlFor="type-piece" className="mb-1 block font-medium">{T.depot.type}</label>
          <select
            id="type-piece" ref={selectRef} value={type}
            onChange={(e) => onTypeChange(e.target.value as TypePiece)}
            className="min-h-11 w-full rounded-md border border-input bg-card px-3"
          >
            {Object.entries(T.depot.types).map(([valeur, libelle]) => (
              <option key={valeur} value={valeur}>{libelle}</option>
            ))}
          </select>
        </div>
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            choisir(e.dataTransfer.files[0]);
          }}
          className="rounded-md border-2 border-dashed border-input p-4 text-center"
          aria-describedby={erreur ? idErreur : undefined}
        >
          <label htmlFor="fichier" className="inline-flex min-h-11 items-center rounded-md border border-primary px-4 font-medium text-primary">
            {T.depot.choisir}
          </label>
          <input
            id="fichier" type="file" className="sr-only" accept="application/pdf,image/png,image/jpeg"
            onChange={(e) => choisir(e.target.files?.[0])}
          />
          <label htmlFor="photo" className="ms-2 inline-flex min-h-11 items-center rounded-md border border-primary px-4 font-medium text-primary lg:hidden">
            {T.depot.photo}
          </label>
          <input
            id="photo" type="file" className="sr-only" accept="image/png,image/jpeg" capture="environment"
            onChange={(e) => choisir(e.target.files?.[0])}
          />
          <p className="mt-2 text-sm text-muted-foreground">{T.depot.glisser}</p>
          {fichier && (
            <div className="mt-3 flex items-center justify-center gap-2">
              {apercu && <img src={apercu} alt="" className="size-16 rounded object-cover" />}
              <span className="text-sm">{fichier.name}</span>
            </div>
          )}
        </div>
        {erreur && (
          <p id={idErreur} role="alert" className="text-sm font-medium text-destructive">{erreur}</p>
        )}
        {info && <p role="status" className="text-sm">{info}</p>}
        {multipage && (
          <Alert><AlertDescription>{T.depot.multipage}</AlertDescription></Alert>
        )}
        <Button type="submit" disabled={!fichier || envoi} className="min-h-11 w-full">
          {T.depot.envoyer}
        </Button>
      </form>
    </Card>
  );
});

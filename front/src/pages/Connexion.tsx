import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { T } from "../textes";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";

export function Connexion() {
  const [identifiant, setIdentifiant] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState(false);
  const naviguer = useNavigate();
  const envoyer = async (e: React.FormEvent) => {
    e.preventDefault();
    setErreur(false);
    try {
      await api.connecter(identifiant, motDePasse);
      naviguer("/");
    } catch {
      setErreur(true);
    }
  };
  return (
    <main className="mx-auto max-w-sm p-4">
      <h1 className="mb-4 text-2xl font-semibold">{T.connexion.titre}</h1>
      <Card className="p-4">
        <form onSubmit={envoyer} className="space-y-4" aria-describedby={erreur ? "erreur-connexion" : undefined}>
          <div className="space-y-1">
            <Label htmlFor="identifiant">{T.connexion.identifiant}</Label>
            <input id="identifiant" autoComplete="username" required value={identifiant}
              onChange={(e) => setIdentifiant(e.target.value)} className="min-h-11 w-full rounded-md border border-input px-3" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="mot-de-passe">{T.connexion.motDePasse}</Label>
            <input id="mot-de-passe" type="password" autoComplete="current-password" required value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)} className="min-h-11 w-full rounded-md border border-input px-3" />
          </div>
          {erreur && <p id="erreur-connexion" role="alert" className="text-sm font-medium text-destructive">{T.connexion.erreur}</p>}
          <Button type="submit" className="min-h-11 w-full">{T.connexion.bouton}</Button>
        </form>
      </Card>
    </main>
  );
}

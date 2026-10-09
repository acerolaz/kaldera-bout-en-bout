import { MessageCircle, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import { ErreurApi, api, type MessageChat } from "../api";
import { T } from "../textes";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  reference: string;
  messages: MessageChat[];
  /** Absent quand le dépôt n'est plus possible : l'action « Déposer maintenant » n'est alors pas affichée. */
  onDeposer?: () => void;
  /** Appelé sur 401 (session expirée) : la page renvoie à la connexion. */
  onExpire?: () => void;
}

// Plein écran par le bas sur mobile, panneau de 400 px à droite dès 1024 px.
const LARGE = "(min-width: 1024px)";
const surLarge = (rappel: () => void) => {
  const m = window.matchMedia?.(LARGE);
  m?.addEventListener("change", rappel);
  return () => m?.removeEventListener("change", rappel);
};
const estLarge = () => window.matchMedia?.(LARGE).matches ?? false;

export function Chat({ reference, messages, onDeposer, onExpire }: Props) {
  const large = useSyncExternalStore(surLarge, estLarge);
  const [ouvert, setOuvert] = useState(false);
  const [texte, setTexte] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [lus, setLus] = useState(0);
  const fin = useRef<HTMLLIElement | null>(null);
  const versDepot = useRef(false);
  const nonLus = messages.slice(lus).some((m) => m.auteur === "agent");

  // Le contenu du Sheet est monté après le premier rendu (Portal) : un ref objet serait encore nul dans
  // l'effet d'ouverture. Le ref callback défile dès que le repère est attaché ; l'effet suit les nouveaux messages.
  const reperer = useCallback((n: HTMLLIElement | null) => {
    fin.current = n;
    n?.scrollIntoView?.({ block: "end" });
  }, []);
  useEffect(() => {
    if (ouvert) setLus(messages.length);
    fin.current?.scrollIntoView?.({ block: "end" });
  }, [ouvert, messages.length]);

  const envoyer = async (e: FormEvent) => {
    e.preventDefault();
    const propre = texte.trim();
    if (!propre || envoi) return;
    setEnvoi(true);
    setErreur(null);
    try {
      await api.envoyer(reference, propre); // les deux messages arrivent par le flux SSE
      setTexte("");
    } catch (err) {
      if (err instanceof ErreurApi && err.statut === 401) onExpire?.();
      else setErreur(err instanceof ErreurApi && err.statut === 429 ? T.chat.trop : T.chat.erreur);
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <Sheet open={ouvert} onOpenChange={setOuvert}>
      <SheetTrigger asChild>
        <Button className="fixed bottom-4 end-4 z-40 min-h-14 rounded-full px-5 shadow-lg">
          <MessageCircle aria-hidden="true" className="size-5" />
          <span>{T.chat.ouvrir}</span>
          {nonLus && (
            <span className="ms-1 inline-block size-2.5 rounded-full bg-or-sur-primaire">
              <span className="sr-only">, {T.chat.nouveau}</span>
            </span>
          )}
        </Button>
      </SheetTrigger>
      <SheetContent
        side={large ? "right" : "bottom"}
        showCloseButton={false}
        // Après « Déposer maintenant », le focus va à la zone de dépôt et non au bouton du chat.
        onCloseAutoFocus={(e) => {
          if (!versDepot.current) return;
          versDepot.current = false;
          e.preventDefault();
          onDeposer?.();
        }}
        className="data-[side=bottom]:h-dvh data-[side=right]:w-[400px] data-[side=right]:sm:max-w-[400px]"
      >
        <SheetHeader className="pe-16">
          <SheetTitle>{T.chat.titre}</SheetTitle>
          <SheetDescription>{T.chat.description}</SheetDescription>
        </SheetHeader>
        <SheetClose asChild>
          <Button variant="ghost" className="absolute end-2 top-2 min-h-11 min-w-11">
            <X aria-hidden="true" />
            <span className="sr-only">{T.chat.fermer}</span>
          </Button>
        </SheetClose>
        <div role="log" className="flex-1 overflow-y-auto px-4">
          <ul className="space-y-3">
            {messages.map((m, i) => (
              <li key={i} className={`max-w-[85%] rounded-lg p-3 whitespace-pre-wrap break-words ${m.auteur === "agent" ? "bg-muted" : "ms-auto border bg-card"}`}>
                <span className="sr-only">{m.auteur === "agent" ? T.chat.agent : T.chat.vous} : </span>
                {m.texte}
                {onDeposer && m.actions.includes("deposer") && (
                  <Button
                    variant="outline"
                    className="mt-2 block min-h-11"
                    onClick={() => {
                      versDepot.current = true;
                      setOuvert(false);
                    }}
                  >
                    {T.chat.deposer}
                  </Button>
                )}
              </li>
            ))}
            <li ref={reperer} aria-hidden="true" />
          </ul>
        </div>
        <form onSubmit={envoyer} className="space-y-2 p-4">
          <Label htmlFor="message-chat">{T.chat.champ}</Label>
          <Textarea
            id="message-chat"
            maxLength={1000}
            value={texte}
            onChange={(e) => setTexte(e.target.value)}
            aria-describedby="compteur-chat"
          />
          <p id="compteur-chat" className="text-end text-sm text-muted-foreground">{T.chat.compteur(texte.length)}</p>
          <p aria-live="polite" className="min-h-5 text-sm text-muted-foreground">{envoi ? T.chat.redaction : ""}</p>
          {erreur && <p role="alert" className="text-sm font-medium text-destructive">{erreur}</p>}
          <Button type="submit" disabled={!texte.trim() || envoi} className="min-h-11 w-full">{T.chat.envoyer}</Button>
        </form>
      </SheetContent>
    </Sheet>
  );
}

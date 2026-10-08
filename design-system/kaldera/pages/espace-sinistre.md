# Espace Sinistre — règles de page

> **PROJECT:** Kaldera · **Page :** espace sinistre (assuré) · spec `docs/superpowers/specs/2026-10-09-ui1-espace-sinistre-design.md`
> Générée par ui-ux-pro-max (« insurance claim tracking timeline upload chat », type *Dashboard / Data View*), puis adaptée.
> Les règles de ce fichier **priment** sur `design-system/kaldera/MASTER.md`. Pour le reste, suivre le Master.

---

## Mise en page

- **Largeur max :** 1200 px, contenu centré.
- **Mobile d'abord (< 1024 px)** : une colonne, dans l'ordre statut → pièces → dépôt → stepper → verdict ; chat en bouton flottant (en bas à droite, 56 px), ouvert en plein écran (`Sheet` shadcn, côté bas).
- **≥ 1024 px** : colonne gauche de 320 px (stepper, pièces) ; colonne droite (statut, dépôt, verdict) ; chat en panneau latéral droit repliable (`Sheet` côté droit, 400 px).
- Aucun défilement horizontal à 375 px ; aucun contenu masqué par l'en-tête fixe.

## Couleurs propres à la page

| Élément | Couleur | Remarque |
|---|---|---|
| En-tête | fond `#14532D`, texte `#FFFFFF`, accent `#FACC15` | 9,11:1 et 5,95:1 |
| Étape franchie | pastille `#166534` + coche | libellé en texte, jamais la couleur seule |
| Étape courante | bordure et pastille `#A16207`, libellé `#0F172A` en gras | `aria-current="step"` |
| Étape à venir | pastille contour `#475569` | — |
| Pièce validée / à refaire / en analyse / à fournir | `#166534` / `#854D0E` / `#475569` / `#0F172A` | icône Lucide + mot écrit |
| Branche « Transmise à un gestionnaire » | même rendu neutre que les autres étapes | jamais de rouge : ce n'est pas une erreur (et ne doit rien laisser deviner) |

## Composants (shadcn/ui + Lucide)

| Zone | Composant | Règles |
|---|---|---|
| Bandeau de statut | `Card` + anneau de progression SVG | anneau = jauge (recommandation `--domain chart`) ; valeur aussi écrite (« 2 min écoulées · environ 1 min restante ») ; `aria-live="polite"` sur le libellé d'étape ; anneau figé si `prefers-reduced-motion` |
| Stepper | `<ol>` maison (pas de composant shadcn natif) | horodatage `<time datetime>` par étape franchie ; branches insérées en retrait sous l'étape concernée |
| Liste des pièces | `Card` + liste | une ligne par pièce : type, statut, raison si « à refaire », bouton « Déposer » qui amène le focus sur la zone de dépôt |
| Dépôt | zone `<label>` + `<input type="file">` | glisser-déposer **et** clic/clavier ; bouton « Prendre une photo » (`capture="environment"`) affiché sur mobile ; `Select` du type de pièce avec `FormLabel` ; aperçu (miniature image, icône + nom pour PDF) ; avertissement PDF multipage en `Alert` sous l'aperçu ; erreur sous la zone, annoncée (`role="alert"`) avec la marche à suivre |
| Soumettre | `Button` plein vert | désactivé tant qu'un fichier est en analyse, avec la raison écrite à côté ; pièces manquantes → `AlertDialog` de confirmation |
| Verdict | `Card` | issue en titre, montant et franchise en tableau `<dl>`, explication en paragraphes courts, pièces retenues en liste |
| Chat | `Sheet` + liste `role="log"` | messages de l'agent à gauche (fond `#EEF2EC`), de l'assuré à droite (fond `#FFFFFF` bordé) ; champ `Textarea` avec `FormLabel` « Votre message » ; compteur 1 000 caractères ; actions rapides en `Button` contour (« Déposer maintenant ») ; indicateur « l'agent rédige… » en `aria-live` |
| Retours courts | `sonner` (`toast.success`, `toast.error`) | dépôt reçu, message envoyé ; jamais pour une erreur bloquante (celle-ci reste sous le champ) |

## Comportements

- **Focus** : laisser `Sheet` et `AlertDialog` gérer le focus (recommandation `--stack shadcn`) ; à la fermeture du chat, le focus revient au bouton qui l'a ouvert.
- **Erreurs** : près du problème, annoncées, avec une issue (« réessayer », « choisir un autre fichier ») — recommandations `--domain ux`.
- **Connexion perdue** : bandeau `Alert` en haut de page (« service momentanément indisponible, vos fichiers n'ont pas été perdus »), reprise silencieuse du flux.
- **Cibles tactiles** ≥ 44 px ; transitions 150–300 ms.

## À ne pas faire sur cette page

- ❌ Afficher un score, un avis, le mot « fraude », un nom d'agent, un état interne ou le mot « repli ».
- ❌ Distinguer visuellement l'escalade vers la cellule fraude de celle vers un gestionnaire.
- ❌ Indiquer un statut par la seule couleur.
- ❌ Effets décoratifs proposés par l'outil pour un tableau de bord commercial (classements, aiguille de jauge animée, « spatial UI ») : sans objet ici.

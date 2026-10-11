# C3-1 · Design system et socle de l'IHM gestionnaire

> Source : `prompt_ui.md` v5, chantier 3 (EX-D51 ; « Conception visuelle — skill `ui-ux-pro-max` » ;
> étape 15 de l'ordre d'implémentation). Branche : `feature/chantier3-c3-1-design-system` · point de
> départ : `9c6843f` (C3-0 fusionné, #13).
> Chantier 3 : C3-0 retrait ✅ → **C3-1 design system et socle** → C3-2 lecture (E1, E2) → C3-3
> temps réel et lots (E3) → C3-4 reprise d'étape → C3-5 documents et recette.

## 1. Objectif

Produire, avec le skill **`ui-ux-pro-max`**, le design system du back-office gestionnaire (clair et
sombre, contraste AA vérifié), puis le **socle** de l'application : coquille, navigation vers
E1 / E2 / E3, bascule de thème mémorisée et composant **`Statut`** (icône + libellé + couleur).
Aucun écran métier n'est livré ici : E1, E2, E3 sont des cadres vides.

| Exigence | Où |
|---|---|
| EX-D51 design system `ui-ux-pro-max`, palette vert / or ajustée par le skill | §2 |
| EX-D51 thème clair / sombre par bouton, système par défaut, mémorisé (`localStorage`) | §3.3 |
| EX-D51 contraste WCAG AA dans les deux thèmes | §2.2, §5 |
| EX-D51 statuts = icône + libellé + couleur, jamais la couleur seule | §3.4 |
| Checklist UX : focus visible, navigation clavier, états vide | §3.2, §5 |

**Critère de sortie** : `npm test`, `npm run lint`, `npm run build`, `make front-e2e` verts ;
`make test` vert (back-end intact) ; cahier de recette régénéré et déroulé (U-01 → U-04 OK) ;
dossier de conception régénéré avec la page design system, sans débordement, copié à la racine du
brief.

### Décisions prises

| Sujet | Décision |
|---|---|
| Typographie | **IBM Plex Sans** (texte, identité actuelle) + **IBM Plex Mono** (références, n° de police, identifiants) ; chiffres tabulaires (`font-variant-numeric: tabular-nums`) pour montants, durées, pourcentages. |
| Thème | Tokens CSS sur `:root` (clair) et `[data-theme="dark"]` (sombre) ; script dans `index.html` avant le rendu (pas de flash) ; hook `useTheme`. **Aucune dépendance** ajoutée (pas de `next-themes`). |
| Variante Tailwind | `@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));` remplace la variante `.dark` de shadcn. |
| Statuts | Un seul composant `<Statut code />` et un catalogue typé `STATUTS` (code → libellé, icône Lucide, ton) ; cinq tons (`neutre`, `info`, `succes`, `attention`, `danger`) — l'« en cours » utilise `info`. Les écrans ne manipulent jamais une couleur. |
| Icônes | Lucide uniquement (déjà installé) ; le ☀️/🌙 du brief devient `Sun` / `Moon` (MASTER : pas d'emoji comme icône). |
| Design system existant | `MASTER.md` régénéré pour le back-office ; `pages/espace-sinistre.md` et `pages/console-admin.md` supprimés, remplacés par `pages/back-office.md`. |
| Composants shadcn | Les 7 composants `ui/*` restent ; ils reçoivent les tokens par `@theme inline` comme aujourd'hui. |

### Hors périmètre

`Toaster`, client API, TanStack Query, tableaux, barres de progression, états chargement / erreur
réels (C3-2 et suivants, au premier écran qui en a besoin) ; toute modification du back-end.

## 2. Design system (`design-system/kaldera/`)

### 2.1 Génération

```bash
python3 <skill>/scripts/search.py "insurance claims back-office operations dashboard data-dense professional sober" \
  --design-system --persist -p "Kaldera" --output-dir <racine du dépôt>
```

puis recherches complémentaires (`--domain color` thème sombre, `--domain ux` tables denses et
états, `--stack shadcn`). Recommandation brute obtenue le 12/10 : style **Data-Dense Dashboard**
(clair et sombre complets, WCAG AA), Fira Sans / Fira Code, bleu `#1E40AF` + ambre `#D97706`.

### 2.2 Adaptations Kaldera (consignées dans `MASTER.md`, tableau « Adaptations Kaldera »)

| Recommandation | Retenu | Raison |
|---|---|---|
| Bleu + ambre | Vert `#14532D` + or `#A16207` (clair) ; vert `#4ADE80` + or `#FACC15` (sombre) | Identité du brief (dossier de conception) |
| Fira Sans / Fira Code | IBM Plex Sans / IBM Plex Mono | Continuité de l'identité, même famille, déjà chargée |
| Pattern « Operations Landing » (hero, CTA) | Application interne : en-tête + contenu | Back-office local, pas une page commerciale |

**Tokens de départ** (vérifiés par `contraste.test.ts`, ajustables si un seuil n'est pas tenu ;
tout ajustement est consigné au journal) :

| Token | Clair | Sombre | Contraste sur carte (clair / sombre) |
|---|---|---|---|
| `--background` / `--card` | `#F8FAFC` / `#FFFFFF` | `#0B1410` / `#111D17` | — |
| `--foreground` | `#0F172A` | `#E6EEE9` | 17,9 / 14,7 |
| `--muted-foreground` | `#475569` | `#9AAFA3` | 7,6 / 7,5 |
| `--primary` / `--primary-foreground` | `#14532D` / `#FFFFFF` | `#4ADE80` / `#052E16` | 9,1 / 8,6 (texte sur bouton) |
| `--ring` (or) | `#A16207` | `#FACC15` | ≥ 3 (4,7 / 12,2 sur fond) |
| `--ton-succes` | `#166534` | `#4ADE80` | 7,1 / 9,9 |
| `--ton-attention` | `#854D0E` | `#FBBF24` | 6,9 / 10,4 |
| `--ton-danger` | `#B91C1C` | `#F87171` | 6,5 / 6,3 |
| `--ton-info` | `#1D4ED8` | `#60A5FA` | 6,7 / 6,8 |
| `--ton-neutre` | `#475569` | `#9AAFA3` | 7,6 / 7,5 |
| `--border` | `#E2E8F0` | `#2A3B32` | décoratif |

Le jeton propre à l'UI1 `--a-refaire` est retiré (remplacé par `--ton-attention`) ; `--or` (accent)
et `--or-sur-primaire` (`#FACC15`, accent de l'en-tête vert en clair, 5,95:1) restent.

### 2.3 `pages/back-office.md`

Règles de page : en-tête (§3.2), largeur max 1440 px, densité (marges serrées, tables à lignes de
40 px, `tabular-nums`), états vide / chargement / erreur (texte + action de récupération, annoncés
par `role="status"` / `role="alert"`), statuts via `<Statut>` uniquement, anti-patterns (couleur
seule, emoji comme icône, or pour du texte courant).

## 3. Socle de l'application (`front/src/`)

### 3.1 Navigation

| Route | Écran C3-1 |
|---|---|
| `/` | E1 « Liste des demandes » : cadre + état vide « Écran livré au sous-projet C3-2 » |
| `/demandes/:reference` | E2 « Dossier {reference} » : cadre + état vide (C3-2) |
| `/lots/:id` | E3 « Lot {id} » : cadre + état vide (C3-3) |
| `*` | 404 « Page introuvable » + lien « Retour à la liste des demandes » |

Chaque page a un `<h1>` unique ; le titre du document suit la page (`Kaldera · <page>`).

### 3.2 Coquille (`components/Coquille.tsx`)

- Lien d'évitement « Aller au contenu » (premier élément focalisable, visible au focus).
- En-tête pleine largeur : marque « Kaldera · back-office gestionnaire », lien « Demandes »
  (`aria-current="page"` sur E1), bouton de thème à droite. Clair : fond `--primary`, texte blanc,
  accent or ; sombre : fond `--card`, bordure `--border`.
- `<main id="contenu" tabIndex={-1}>`, largeur max 1440 px.

### 3.3 Thème (`theme.ts`, `useTheme.ts`, `index.html`)

| Élément | Comportement |
|---|---|
| Stockage | clé `kaldera.theme`, valeurs `clair` / `sombre` ; absent ⇒ thème système |
| Système | sans choix enregistré, suit `prefers-color-scheme` **en direct** (`matchMedia` change) |
| Bouton | bascule et enregistre le choix ; icône `Moon` en clair (« Passer au thème sombre »), `Sun` en sombre (« Passer au thème clair ») ; `aria-label` explicite |
| Script `index.html` | pose `document.documentElement.dataset.theme` avant le rendu React ; accès `localStorage` dans `try/catch` (navigation privée ⇒ système) |
| `color-scheme` | `:root { color-scheme: light }` / `[data-theme="dark"] { color-scheme: dark }` (barres de défilement, champs natifs) |

### 3.4 Statut (`statuts.ts`, `components/Statut.tsx`)

`<Statut code="repli" />` ⇒ `<span>` avec icône Lucide (`aria-hidden`) + libellé ; la couleur vient
du ton. Code absent du catalogue ⇒ ton `neutre`, libellé = code brut (jamais d'exception).

| Famille | Code → libellé (icône, ton) |
|---|---|
| Demande | `admission` → En analyse (`FileSearch`, info) · `en_cours` → En traitement (`Loader`, info) · `terminee` → Terminée (`CircleCheck`, succes) · `secours` → Fiche de secours (`LifeBuoy`, attention) |
| Issue | `acceptee` → Acceptée (`CircleCheck`, succes) · `refusee` → Refusée (`CircleX`, danger) · `escalade` → Escaladée (`UserRound`, attention) |
| Étape | `en_attente` → En attente (`Clock`, neutre) · `en_cours` → En cours (`Loader`, info) · `termine` → Terminée (`CircleCheck`, succes) · `sautee` → Sautée (`SkipForward`, neutre) · `echec` → Échec (`CircleX`, danger) · `repli` → Repli déterministe (`RotateCcw`, attention) · `degrade` → Mode dégradé (`LifeBuoy`, attention) |
| Badges | `mode_degrade` → Mode dégradé (`LifeBuoy`, attention) · `borne` → Borne atteinte (`OctagonX`, danger) |

`en_cours` est commun à la demande et à l'étape : un seul code, même rendu. Les codes sont ceux du
code (`demandes.statut`, `Issue.decision` / `issue`, statuts d'étape du brief).

### 3.5 Tests

| Fichier | Vérifie |
|---|---|
| `test/contraste.test.ts` | chaque paire du §2.2, **dans chaque thème** (blocs `:root` et `[data-theme="dark"]` lus séparément dans `index.css`) |
| `theme.test.ts` | choix enregistré respecté ; défaut système (clair et sombre) ; bascule ⇒ enregistrée ; `localStorage` qui lève ⇒ système, sans exception ; suivi du système en direct sans choix |
| `components/Statut.test.tsx` | chaque code du catalogue : libellé visible, icône `aria-hidden` ; code inconnu ⇒ neutre + code brut ; axe |
| `App.test.tsx` | chaque route rend son `<h1>` ; 404 ; lien d'évitement ; bouton de thème accessible ; axe |
| `e2e/fumee.spec.ts` | E1 s'affiche ; bascule ⇒ sombre, persiste après rechargement ; axe dans les deux thèmes ; Tab ⇒ lien d'évitement puis « Demandes » puis bouton de thème |

## 4. Documents

| Document | Mise à jour |
|---|---|
| Cahier de recette (générateur + PDF, déroulé) | S-04 : « Vite sert le back-office gestionnaire » ; section 2 : **U-01** E1 et en-tête ; **U-02** bascule clair / sombre mémorisée, défaut système ; **U-03** clavier : lien d'évitement, « Demandes », bouton de thème, anneau or visible dans les deux thèmes ; **U-04** `/demandes/KAL-26-0101`, `/lots/1` (cadres E2 / E3), adresse inconnue ⇒ 404 + retour. `STATUTS` renseignés après déroulé. |
| Dossier de conception (`make dossier` + copie à la racine) | nouvelle page `298-ihm-design-system.html`, section « 2.8 IHM gestionnaire : design system » (profil et écarts `ui-ux-pro-max`, tableau des tokens et contrastes, catalogue des statuts, mécanisme du thème) ; sommaire ; glossaire (design system, token, thème clair / sombre). |
| `README.md` | section IHM : `make front`, thème, design system, captures clair / sombre (`docs/captures/`). |
| `docs/journal_ajustements.md` | une ligne si un token est ajusté pour tenir AA. |

## 5. Risques

| Risque | Parade |
|---|---|
| Flash du mauvais thème au chargement | script synchrone dans `<head>` avant le bundle ; vérifié par le test e2e (thème présent dès le premier rendu) |
| shadcn suppose `.dark` | variante Tailwind redéfinie sur `[data-theme=dark]` ; tokens shadcn (`--card`, `--primary`…) redéfinis dans les deux blocs |
| Contraste d'un ton insuffisant en sombre | `contraste.test.ts` par thème bloque ; ajustement consigné |
| Vert primaire et vert succès proches | un statut porte toujours icône + libellé ; le bouton primaire n'est jamais un statut |

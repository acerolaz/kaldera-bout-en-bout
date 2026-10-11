# Design System Master File

> **LOGIC:** When building a specific page, first check `design-system/kaldera/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** Kaldera
**Generated:** 2026-10-12 01:09:30 (`ui-ux-pro-max` 2.11.0, adapté au back-office gestionnaire)
**Category:** Analytics Dashboard
**Style:** Data-Dense Dashboard

---

## Global Rules

### Color Palette

Deux thèmes, mêmes noms de variables : `:root` (clair) et `[data-theme="dark"]` (sombre). Les contrastes sont donnés sur la carte (`--card`) ; ils sont vérifiés par `contraste.test.ts`, thème par thème.

#### Thème clair

| Rôle | Hex | Variable CSS | Contraste sur carte |
|------|-----|--------------|---------------------|
| Fond | `#F8FAFC` | `--background` | — |
| Carte | `#FFFFFF` | `--card` | — |
| Texte | `#0F172A` | `--foreground` | 17,9 |
| Texte secondaire | `#475569` | `--muted-foreground` | 7,6 |
| Primaire | `#14532D` | `--primary` | 9,1 (texte blanc `--primary-foreground` `#FFFFFF` sur bouton) |
| Anneau de focus (or) | `#A16207` | `--ring` | ≥ 3 (4,7 sur fond) |
| Or sur primaire | `#FACC15` | `--or-sur-primaire` | 5,95 sur `#14532D` |
| Succès | `#166534` | `--ton-succes` | 7,1 |
| Attention | `#854D0E` | `--ton-attention` | 6,9 |
| Danger | `#B91C1C` | `--ton-danger` | 6,5 |
| Info | `#1D4ED8` | `--ton-info` | 6,7 |
| Neutre | `#475569` | `--ton-neutre` | 7,6 |
| Bordure | `#E2E8F0` | `--border` | décoratif |

#### Thème sombre

| Rôle | Hex | Variable CSS | Contraste sur carte |
|------|-----|--------------|---------------------|
| Fond | `#0B1410` | `--background` | — |
| Carte | `#111D17` | `--card` | — |
| Texte | `#E6EEE9` | `--foreground` | 14,7 |
| Texte secondaire | `#9AAFA3` | `--muted-foreground` | 7,5 |
| Primaire | `#4ADE80` | `--primary` | 8,6 (texte `--primary-foreground` `#052E16` sur bouton) |
| Anneau de focus (or) | `#FACC15` | `--ring` | ≥ 3 (12,2 sur fond) |
| Succès | `#4ADE80` | `--ton-succes` | 9,9 |
| Attention | `#FBBF24` | `--ton-attention` | 10,4 |
| Danger | `#F87171` | `--ton-danger` | 6,3 |
| Info | `#60A5FA` | `--ton-info` | 6,8 |
| Neutre | `#9AAFA3` | `--ton-neutre` | 7,5 |
| Bordure | `#2A3B32` | `--border` | décoratif |

`--or` (accent) et `--or-sur-primaire` sont conservés ; `--a-refaire` est retiré (remplacé par `--ton-attention`). Les tons `--ton-*` colorent les statuts (voir « Statuts »).

**Color Notes:** vert + or (identité Kaldera), tons de statut séparés. Recherche `--domain color` : sur fond sombre, éclaircir les teintes (variantes 400) plutôt que reprendre les teintes du clair ; viser 4,5:1 minimum pour le texte.

### Typography

- **Heading Font:** IBM Plex Sans
- **Body Font:** IBM Plex Sans
- **Mono Font:** IBM Plex Mono (références, n° de police, identifiants)
- **Chiffres:** `font-variant-numeric: tabular-nums` pour montants, durées et pourcentages
- **Mood:** dashboard, data, précis, sobre
- **Google Fonts:** [IBM Plex Sans + IBM Plex Mono](https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap)

**CSS Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
```

### Spacing Variables

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` / `0.25rem` | Tight gaps |
| `--space-sm` | `8px` / `0.5rem` | Icon gaps, inline spacing |
| `--space-md` | `16px` / `1rem` | Standard padding |
| `--space-lg` | `24px` / `1.5rem` | Section padding |
| `--space-xl` | `32px` / `2rem` | Large gaps |
| `--space-2xl` | `48px` / `3rem` | Section margins |

### Shadow Depths

| Level | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle lift |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | Modals, dropdowns |

Les cartes de données n'ont pas d'ombre : séparation par bordure `--border`.

---

## Component Specs

### Buttons

```css
/* Primary Button */
.btn-primary {
  background: var(--primary);
  color: var(--primary-foreground);
  padding: 8px 16px;
  border-radius: 8px;
  font-weight: 600;
  transition: background-color 200ms ease;
  cursor: pointer;
}

.btn-primary:hover {
  opacity: 0.9;
}

/* Secondary Button */
.btn-secondary {
  background: transparent;
  color: var(--primary);
  border: 1px solid var(--primary);
  padding: 8px 16px;
  border-radius: 8px;
  font-weight: 600;
  transition: background-color 200ms ease;
  cursor: pointer;
}
```

### Cards

```css
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
}

/* Cartes non cliquables : pas d'effet de survol (évite de suggérer une action) */
```

### Inputs

```css
.input {
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 16px;
  transition: border-color 200ms ease;
}

.input:focus-visible {
  border-color: var(--primary);
  outline: none;
  box-shadow: 0 0 0 3px var(--ring);  /* anneau or */
}
```

### Modals

```css
.modal-overlay {
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
}

.modal {
  background: var(--card);
  border-radius: 16px;
  padding: 32px;
  box-shadow: var(--shadow-lg);
  max-width: 500px;
  width: 90%;
}
```

---

## Style Guidelines

**Style:** Data-Dense Dashboard

**Keywords:** données denses, tableaux, marges serrées, lisibilité, statuts explicites, aucune information superflue

**Best For:** Business intelligence dashboards, operational dashboards, enterprise reporting

**Key Effects:** transitions de 150–300 ms sur les changements d'état ; mise en évidence de la ligne au survol ; aucune animation décorative ; `prefers-reduced-motion` respecté.

Recherches complémentaires : `--domain ux` (états vide / chargement : message utile, squelette ; anneau de focus visible sur chaque élément interactif), `--stack shadcn` (définir les deux jeux de couleurs ; ici `[data-theme="dark"]` remplace la classe `.dark`, via `@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));`).

### Page Pattern

**Pattern Name:** Application interne de back-office (pas de page d'accueil)

- En-tête + contenu : pas de hero, de logos clients ni de CTA commercial.
- Une action principale par écran ; les actions secondaires en contour.
- Signaux de confiance discrets : références, horodatages, statuts écrits en toutes lettres.

### Statuts

Règle : **icône + libellé + couleur, jamais la couleur seule** ; un statut passe toujours par `<Statut code />` (jamais une classe de couleur dans un écran). Code inconnu : ton `neutre`, libellé = code brut. Icônes Lucide, `aria-hidden`.

| Famille | Code | Libellé | Icône Lucide | Ton |
|---|---|---|---|---|
| Demande | `admission` | En analyse | `FileSearch` | info |
| Demande / Étape | `en_cours` | En traitement | `Loader` | info |
| Demande | `terminee` | Terminée | `CircleCheck` | succes |
| Demande | `secours` | Fiche de secours | `LifeBuoy` | attention |
| Issue | `acceptee` | Acceptée | `CircleCheck` | succes |
| Issue | `refusee` | Refusée | `CircleX` | danger |
| Issue | `escalade` | Escaladée | `UserRound` | attention |
| Étape | `en_attente` | En attente | `Clock` | neutre |
| Étape | `termine` | Terminée | `CircleCheck` | succes |
| Étape | `sautee` | Sautée | `SkipForward` | neutre |
| Étape | `echec` | Échec | `CircleX` | danger |
| Étape | `repli` | Repli déterministe | `RotateCcw` | attention |
| Étape | `degrade` | Mode dégradé | `LifeBuoy` | attention |
| Badge | `mode_degrade` | Mode dégradé | `LifeBuoy` | attention |
| Badge | `borne` | Borne atteinte | `OctagonX` | danger |

`en_cours` est un seul code, commun à la demande et à l'étape, avec un seul rendu (« En traitement », `Loader`, info).

### Thème

- Tokens sur `:root` (clair) et `[data-theme="dark"]` (sombre) ; `color-scheme: light` / `dark`.
- Clé `localStorage` `kaldera.theme` (`clair` / `sombre`) ; absente ou invalide : thème système, suivi en direct.
- Bouton de bascule : icône `Moon` en clair (« Passer au thème sombre »), `Sun` en sombre (« Passer au thème clair »).
- Script synchrone dans `index.html` avant le rendu (pas de flash).

---

## Adaptations Kaldera (écarts avec la recommandation générée)

| Recommandation de l'outil | Retenu | Raison |
|---|---|---|
| Bleu `#1E40AF` + ambre `#D97706` | Vert `#14532D` + or `#A16207` (clair) ; vert `#4ADE80` + or `#FACC15` (sombre) | Identité du brief (dossier de conception) |
| Fira Sans / Fira Code | IBM Plex Sans / IBM Plex Mono | Continuité de l'identité, même famille, déjà chargée |
| Pattern « Operations Landing » (hero, CTA) | Application interne : en-tête + contenu | Back-office local, pas une page commerciale |
| Anneau de focus or `#A16207` | `#FACC15` (`--or-sur-primaire`) dans l'en-tête vert | `#A16207` sur `#14532D` ne fait que 1,85:1, insuffisant |
| Cartes avec ombre et levée au survol | Cartes à bordure, sans effet de survol | Densité ; une carte qui bouge suggère une action inexistante |

---

## Anti-Patterns (Do NOT Use)

- ❌ Statut indiqué par la seule couleur
- ❌ Emoji comme icône
- ❌ Or utilisé pour le texte courant
- ❌ Ornate design
- ❌ No filtering

### Additional Forbidden Patterns

- ❌ **Emojis as icons** — Use SVG icons (Lucide)
- ❌ **Missing cursor:pointer** — All clickable elements must have cursor:pointer
- ❌ **Layout-shifting hovers** — Avoid scale transforms that shift layout
- ❌ **Low contrast text** — Maintain 4.5:1 minimum contrast ratio
- ❌ **Instant state changes** — Always use transitions (150-300ms)
- ❌ **Invisible focus states** — Focus states must be visible for a11y

---

## Pre-Delivery Checklist

Before delivering any UI code, verify:

- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons from Lucide
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover states with smooth transitions (150-300ms)
- [ ] Light mode: text contrast 4.5:1 minimum
- [ ] Dark mode : contraste 4.5:1 minimum
- [ ] Focus visible dans l'en-tête et dans le contenu
- [ ] `prefers-reduced-motion` respected
- [ ] Responsive: 375px, 768px, 1024px, 1440px
- [ ] No content hidden behind fixed navbars
- [ ] No horizontal scroll on mobile

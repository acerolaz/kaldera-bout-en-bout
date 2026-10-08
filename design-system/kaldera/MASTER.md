# Design System Master File

> **LOGIC:** When building a specific page, first check `design-system/kaldera/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** Kaldera
**Generated:** 2026-10-09 01:53:13
**Category:** Insurance Platform

---

## Global Rules

### Color Palette

| Role | Hex | CSS Variable |
|------|-----|--------------|
| Primary | `#14532D` | `--color-primary` |
| On Primary | `#FFFFFF` | `--color-on-primary` |
| Secondary | `#166534` | `--color-secondary` |
| Accent/CTA | `#14532D` | `--color-accent` |
| Background | `#F8FAFC` | `--color-background` |
| Foreground | `#0F172A` | `--color-foreground` |
| Muted | `#EEF2EC` | `--color-muted` |
| Border | `#E2E8F0` | `--color-border` |
| Destructive | `#B91C1C` | `--color-destructive` |
| Ring | `#A16207` | `--color-ring` |
| Accent or | `#A16207` | `--color-gold` |
| Or sur vert | `#FACC15` | `--color-gold-on-primary` |
| Muted foreground | `#475569` | `--color-muted-foreground` |
| Succès | `#166534` | `--color-success` |
| À refaire | `#854D0E` | `--color-warning` |

**Color Notes:** Identité Kaldera vert foncé + or (voir « Adaptations Kaldera »).

| Paire | Contraste | Usage autorisé |
|---|---|---|
| `#0F172A` sur `#F8FAFC` | 17,06:1 | texte courant |
| `#14532D` sur `#FFFFFF` | 9,11:1 | boutons, titres, texte |
| `#166534` sur `#FFFFFF` | 7,13:1 | statut « validée », liens |
| `#475569` sur `#F8FAFC` | 7,24:1 | texte secondaire |
| `#B91C1C` sur `#FFFFFF` | 6,47:1 | erreurs |
| `#854D0E` sur `#FFFFFF` | 6,85:1 | statut « à refaire » |
| `#A16207` sur `#FFFFFF` | 4,92:1 | **accents** : bordure de l'étape courante, icônes, anneau de focus (≥ 3:1) |
| `#FACC15` sur `#14532D` | 5,95:1 | or sur l'en-tête vert |

### Typography

- **Heading Font:** IBM Plex Sans
- **Body Font:** IBM Plex Sans
- **Mood:** financial, trustworthy, professional, corporate, banking, serious
- **Google Fonts:** [IBM Plex Sans + IBM Plex Sans](https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap)

**CSS Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');
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
| `--space-3xl` | `64px` / `4rem` | Hero padding |

### Shadow Depths

| Level | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle lift |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.1)` | Cards, buttons |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | Modals, dropdowns |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.15)` | Hero images, featured cards |

---

## Component Specs

### Buttons

```css
/* Primary Button */
.btn-primary {
  background: #14532D;
  color: white;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

/* Secondary Button */
.btn-secondary {
  background: transparent;
  color: #14532D;
  border: 2px solid #14532D;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}
```

### Cards

```css
.card {
  background: #F8FAFC;
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow-md);
  transition: all 200ms ease;
}

/* Cartes non cliquables : pas d'effet de survol (évite de suggérer une action) */
```

### Inputs

```css
.input {
  padding: 12px 16px;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  font-size: 16px;
  transition: border-color 200ms ease;
}

.input:focus {
  border-color: #14532D;
  outline: none;
  box-shadow: 0 0 0 3px #A16207;  /* anneau or, 4,71:1 sur le fond */
}
```

### Modals

```css
.modal-overlay {
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
}

.modal {
  background: white;
  border-radius: 16px;
  padding: 32px;
  box-shadow: var(--shadow-xl);
  max-width: 500px;
  width: 90%;
}
```

---

## Style Guidelines

**Style:** Trust & Authority

**Keywords:** sobriété, lisibilité, statuts explicites, horodatages, aucune information superflue

**Best For:** Healthcare/medical landing pages, financial services, enterprise software, premium/luxury products, legal services

**Key Effects:** transitions de 150–300 ms sur les changements de statut ; aucune animation décorative (carrousel, pulsation) ; `prefers-reduced-motion` coupe l'anneau animé.

### Page Pattern

**Pattern Name:** Espace client authentifié (application, pas une page d'accueil)

- Pas de hero, de logos clients ni de CTA « Contact Sales » : l'assuré est connecté et vient suivre **son** dossier.
- Une action principale par écran (déposer, soumettre), en bouton plein vert ; les actions secondaires en contour.
- Signaux de confiance discrets : référence du dossier, horodatages, statuts écrits en toutes lettres.

---

## Adaptations Kaldera (écarts avec la recommandation générée)

| Recommandation de l'outil | Retenu | Raison |
|---|---|---|
| Bleu « confiance » `#2563EB` + CTA orange `#EA580C` | Vert foncé `#14532D` + or `#A16207` | Contrainte d'identité du brief. Compatible : la recherche `--domain color` propose elle-même « Trust navy + premium gold » (`#A16207`) pour la finance traditionnelle ; le vert foncé remplace le bleu marine en restant largement au-dessus du seuil AA (9,11:1 sur blanc). |
| CTA de couleur d'accent | CTA vert plein, l'or en accent seulement | Un bouton or porterait du texte blanc à 4,92:1, juste au-dessus du seuil ; le vert donne 9,11:1. |
| Page « Enterprise Gateway » (hero, Contact Sales) | Espace client authentifié | La recommandation vise une page d'accueil commerciale, pas un espace privé. |
| Cartes cliquables avec effet de levée | Cartes statiques | Une carte qui bouge au survol suggère une action qui n'existe pas. |
| Anneau de focus bleu | Anneau or `#A16207` (4,71:1 sur le fond) | Visible et distinct du vert des boutons. |

Recherches complémentaires utilisées : `--domain ux` (erreurs annoncées par `aria-live` ou `role=alert`, erreur sous le champ, chemin de récupération, validation au blur, types d'input), `--domain chart` (jauge ou bullet chart pour un avancement → anneau de progression), `--stack shadcn` (laisser Dialog et Sheet gérer le focus, toasts sémantiques `sonner`, `FormLabel` obligatoire, jamais le placeholder seul).

## Anti-Patterns (Do NOT Use)

- ❌ Exposer un état interne, un score ou une information anti-fraude à l'assuré
- ❌ Statut indiqué par la seule couleur
- ❌ Or utilisé pour le texte courant
- ❌ AI purple/pink gradients

### Additional Forbidden Patterns

- ❌ **Emojis as icons** — Use SVG icons (Heroicons, Lucide, Simple Icons)
- ❌ **Missing cursor:pointer** — All clickable elements must have cursor:pointer
- ❌ **Layout-shifting hovers** — Avoid scale transforms that shift layout
- ❌ **Low contrast text** — Maintain 4.5:1 minimum contrast ratio
- ❌ **Instant state changes** — Always use transitions (150-300ms)
- ❌ **Invisible focus states** — Focus states must be visible for a11y

---

## Pre-Delivery Checklist

Before delivering any UI code, verify:

- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons from consistent icon set (Heroicons/Lucide)
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover states with smooth transitions (150-300ms)
- [ ] Light mode: text contrast 4.5:1 minimum
- [ ] Focus states visible for keyboard navigation
- [ ] `prefers-reduced-motion` respected
- [ ] Responsive: 375px, 768px, 1024px, 1440px
- [ ] No content hidden behind fixed navbars
- [ ] No horizontal scroll on mobile

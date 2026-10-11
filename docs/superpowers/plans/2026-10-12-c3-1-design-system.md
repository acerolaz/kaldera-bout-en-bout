# C3-1 · Design system et socle de l'IHM gestionnaire — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produire avec `ui-ux-pro-max` le design system clair / sombre du back-office gestionnaire, puis le socle React : coquille, routes E1 / E2 / E3 / 404, thème mémorisé sans flash, composant `Statut`.

**Architecture:** Tokens CSS dans `front/src/index.css` (`:root` clair, `[data-theme="dark"]` sombre) lus par Tailwind 4 via `@theme inline` et par shadcn ; un script synchrone dans `index.html` pose `data-theme` avant le rendu, `theme.ts` / `useTheme.ts` gèrent la bascule. Un catalogue typé `statuts.ts` alimente `<Statut code />`. `App.tsx` = `BrowserRouter` + `Routage` (coquille + pages cadres).

**Tech Stack:** React 19, TypeScript, Vite 8, Tailwind 4, shadcn/ui, lucide-react, react-router-dom 7, Vitest + Testing Library + vitest-axe, Playwright + @axe-core/playwright ; `ui-ux-pro-max` (script Python) ; reportlab (cahier) ; `docs/conception/rendre.cjs` (dossier).

**Spec:** `docs/superpowers/specs/2026-10-12-c3-1-design-system-design.md`

Commandes front depuis `front/` ; les autres depuis la racine du dépôt (`src/kaldera-bout-en-bout/`).

## Global Constraints

- Branche `feature/chantier3-c3-1-design-system` (spec commitée, `4e09c26`). Aucune modification du back-end (`src/`, `tests/` Python).
- **Aucune dépendance npm ajoutée** (pas de `next-themes`) ; icônes Lucide uniquement, jamais d'emoji comme icône.
- Typographie : IBM Plex Sans (texte) + IBM Plex Mono (références, identifiants) ; `tabular-nums` pour montants, durées, pourcentages.
- Thème : clé `localStorage` `kaldera.theme`, valeurs `clair` / `sombre` ; absente ⇒ thème système suivi en direct ; attribut `data-theme` = `light` / `dark` sur `<html>`.
- Variante Tailwind : `@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));`
- Tokens (valeurs exactes du §2.2 de la spec) ; tons de statut : `--ton-neutre`, `--ton-info`, `--ton-succes`, `--ton-attention`, `--ton-danger` ; `--a-refaire` retiré ; `--or` et `--or-sur-primaire` conservés.
- Catalogue des statuts (codes, libellés, icônes, tons) : tableau §3.4 de la spec, à l'identique.
- Libellés exacts : marque « Kaldera · back-office gestionnaire » ; lien « Demandes » ; lien d'évitement « Aller au contenu » ; bouton « Passer au thème sombre » / « Passer au thème clair » ; h1 « Liste des demandes », « Dossier {reference} », « Lot {id} », « Page introuvable » ; lien 404 « Retour à la liste des demandes ».
- Textes et commentaires en français, style du code existant.
- Commits terminés par une ligne `Co-Authored-By:` nommant le modèle qui a réellement écrit le commit.

## Review Focus

1. **Anneau de focus dans l'en-tête vert** (clair) : l'or `#A16207` sur `#14532D` ne fait que 1,85:1 ; le focus des éléments de l'en-tête doit utiliser `--or-sur-primaire` (`#FACC15`, 5,95:1) → paire testée en Task 2, classe imposée en Task 5.
2. **`localStorage` indisponible** (navigation privée, cookies bloqués) : la page s'affiche au thème système, le bouton bascule quand même pour la session, aucune exception → tests Task 3.
3. **Code de statut hostile ou inconnu** (`"constructor"`, `"toString"`, `""`) : rendu neutre avec le code brut, jamais une fonction du prototype ni un plantage → test Task 4 (`Object.hasOwn`).
4. **Choix enregistré corrompu** (`kaldera.theme = "bleu"`) : traité comme absent ⇒ thème système → test Task 3 et script `index.html`.
5. **Rechargement en thème sombre** : pas de flash clair ; `data-theme="dark"` présent avant le rendu React → test e2e Task 5.

---

### Task 1: Design system généré avec `ui-ux-pro-max`

**Files:**
- Modify (régénéré puis adapté): `design-system/kaldera/MASTER.md`
- Create: `design-system/kaldera/pages/back-office.md`
- Delete: `design-system/kaldera/pages/espace-sinistre.md`, `design-system/kaldera/pages/console-admin.md`

**Interfaces:**
- Produces: les valeurs de tokens et règles que les Tasks 2 à 5 appliquent (identiques à la spec §2.2 et §3.4).

- [ ] **Step 1: Générer la recommandation persistée**

```bash
SKILL=/Users/chico/.claude/plugins/cache/ui-ux-pro-max-skill/ui-ux-pro-max/2.11.0/.claude/skills/ui-ux-pro-max/scripts/search.py
python3 "$SKILL" "insurance claims back-office operations dashboard data-dense professional sober" \
  --design-system --persist -p "Kaldera" --output-dir "$(pwd)"
python3 "$SKILL" "dark mode dashboard green gold accessible" --domain color
python3 "$SKILL" "data table dense empty loading error states keyboard" --domain ux
python3 "$SKILL" "dark mode theme toggle data-theme" --stack shadcn
```

Expected : `design-system/kaldera/MASTER.md` réécrit (style Data-Dense Dashboard, Fira, bleu / ambre) ; noter les règles utiles des trois recherches.

- [ ] **Step 2: Adapter `MASTER.md` au back-office Kaldera**

Remplacer dans le fichier généré :
- **Color Palette** : deux tableaux « Thème clair » et « Thème sombre » avec exactement les tokens du §2.2 de la spec (rôle, hex, variable CSS, contraste sur carte) ; tons `--ton-*`.
- **Typography** : IBM Plex Sans + IBM Plex Mono ; import Google Fonts `family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500` ; `tabular-nums` pour les chiffres.
- **Page Pattern** : « Application interne de back-office (pas de page d'accueil) » : en-tête + contenu, pas de hero ni de CTA commercial.
- **Statuts** : le catalogue du §3.4 de la spec (code, libellé, icône Lucide, ton) et la règle « icône + libellé + couleur, jamais la couleur seule ; un statut passe toujours par `<Statut>` ».
- **Thème** : `:root` / `[data-theme="dark"]`, clé `kaldera.theme`, défaut système, bouton `Sun` / `Moon`.
- Section **« Adaptations Kaldera (écarts avec la recommandation générée) »** : le tableau du §2.2 de la spec (bleu + ambre → vert / or ; Fira → Plex ; Operations Landing → application interne) + la ligne « Anneau de focus or `#A16207` → `#FACC15` dans l'en-tête vert (1,85:1 insuffisant) ».
- **Anti-Patterns** : garder couleur seule, emoji comme icône, or pour du texte courant ; retirer « Exposer un état interne… à l'assuré » (UI1).
- **Pre-Delivery Checklist** : ajouter « Dark mode : contraste 4.5:1 minimum » et « Focus visible dans l'en-tête et dans le contenu ».

- [ ] **Step 3: Écrire `pages/back-office.md` et supprimer les pages UI1**

Créer `design-system/kaldera/pages/back-office.md` :

```markdown
# Back-office gestionnaire — règles de page

> **PROJECT:** Kaldera · **Page :** back-office gestionnaire (E1, E2, E3) · spec `docs/superpowers/specs/2026-10-12-c3-1-design-system-design.md`
> Les règles de ce fichier **priment** sur `design-system/kaldera/MASTER.md`. Pour le reste, suivre le Master.

## Mise en page
- En-tête pleine largeur, hauteur 48 px : marque « Kaldera · back-office gestionnaire », lien « Demandes », bouton de thème à droite.
  Clair : fond `--primary`, texte blanc, accent et **anneau de focus** `--or-sur-primaire`. Sombre : fond `--card`, bordure `--border`, anneau `--ring`.
- Lien d'évitement « Aller au contenu », premier élément focalisable, visible au focus.
- Contenu : `<main id="contenu">`, largeur max 1440 px, marges 16 px ; un seul `<h1>` par page.

## Densité
- Tableaux : lignes de 40 px, en-têtes collants, `tabular-nums` pour montants, durées, pourcentages ; références et n° de police en IBM Plex Mono.
- Pas d'ombre portée sur les cartes de données ; séparation par bordure `--border`.

## États
- Vide : phrase qui dit ce qui manque et ce qui le fera apparaître.
- Chargement : squelettes de même hauteur que le contenu attendu ; `aria-busy="true"` sur la zone.
- Erreur : message + action de récupération (« Réessayer ») ; `role="alert"`.

## Statuts
- Toujours `<Statut code />` (icône + libellé + couleur) ; jamais une couleur seule, jamais une classe de couleur dans un écran.

## Anti-patterns
- ❌ Statut par la couleur seule · ❌ Emoji comme icône · ❌ Or pour du texte courant · ❌ Anneau de focus or foncé sur l'en-tête vert
```

```bash
git rm design-system/kaldera/pages/espace-sinistre.md design-system/kaldera/pages/console-admin.md
```

- [ ] **Step 4: Vérifier**

Run: `grep -n -i -E 'assur|Fira|#1E40AF|#D97706|console-admin|espace-sinistre' design-system/kaldera/MASTER.md design-system/kaldera/pages/back-office.md`
Expected : seules les lignes du tableau « Adaptations Kaldera » citent Fira / `#1E40AF` / `#D97706` ; aucune mention de l'assuré.

- [ ] **Step 5: Commit**

```bash
git add -A design-system
git commit -m "docs(design-system): back-office gestionnaire généré avec ui-ux-pro-max (clair / sombre, vert / or)"
```

---

### Task 2: Tokens clair / sombre et contraste par thème

**Files:**
- Modify: `front/src/index.css` (réécrit)
- Modify: `front/index.html:8` (lien Google Fonts)
- Test: `front/src/test/contraste.test.ts` (réécrit)

**Interfaces:**
- Produces: variables CSS et classes Tailwind `bg-background`, `bg-card`, `text-foreground`, `text-muted-foreground`, `bg-primary`, `text-primary-foreground`, `text-or`, `text-or-sur-primaire`, `outline-or-sur-primaire`, `text-ton-neutre`, `text-ton-info`, `text-ton-succes`, `text-ton-attention`, `text-ton-danger`, `font-mono` ; variante `dark:` branchée sur `[data-theme=dark]`.

- [ ] **Step 1: Réécrire le test de contraste (rouge)**

Remplacer `front/src/test/contraste.test.ts` par :

```ts
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(path.resolve(process.cwd(), "src/index.css"), "utf-8"); // cwd = front/
const bloc = (selecteur: string): string => {
  const debut = css.indexOf(`${selecteur} {`);
  if (debut < 0) throw new Error(`bloc ${selecteur} absent de index.css`);
  return css.slice(debut, css.indexOf("}", debut));
};
const THEMES = { clair: bloc(":root"), sombre: bloc('[data-theme="dark"]') };
type Theme = keyof typeof THEMES;
const jeton = (theme: Theme, nom: string): string => {
  const m = THEMES[theme].match(new RegExp(`--${nom}:\\s*(#[0-9A-Fa-f]{6})`));
  if (!m) throw new Error(`jeton --${nom} absent du thème ${theme}`);
  return m[1];
};
const luminance = (hex: string): number => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
};
const contraste = (a: string, b: string): number => {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

const TONS = ["ton-neutre", "ton-info", "ton-succes", "ton-attention", "ton-danger"];
const PAIRES: [string, string, number][] = [
  ["foreground", "background", 4.5],
  ["foreground", "card", 4.5],
  ["muted-foreground", "background", 4.5],
  ["muted-foreground", "card", 4.5],
  ["muted-foreground", "muted", 4.5],
  ["primary-foreground", "primary", 4.5],
  ["destructive", "card", 4.5],
  ...TONS.flatMap((ton): [string, string, number][] => [
    [ton, "card", 4.5],
    [ton, "background", 4.5],
    [ton, "muted", 4.5],
  ]),
  ["ring", "background", 3],
  ["ring", "card", 3],
  ["or", "card", 3],
];

describe.each(Object.keys(THEMES) as Theme[])("contrastes du thème %s (WCAG AA)", (theme) => {
  it.each(PAIRES)("%s sur %s ≥ %s:1", (texte, fond, seuil) => {
    expect(contraste(jeton(theme, texte), jeton(theme, fond))).toBeGreaterThanOrEqual(seuil);
  });
});

describe("en-tête vert (thème clair)", () => {
  it("le texte et l'anneau de focus or clair tiennent sur le vert", () => {
    expect(contraste(jeton("clair", "primary-foreground"), jeton("clair", "primary"))).toBeGreaterThanOrEqual(4.5);
    expect(contraste(jeton("clair", "or-sur-primaire"), jeton("clair", "primary"))).toBeGreaterThanOrEqual(3);
  });
});
```

- [ ] **Step 2: Vérifier qu'il échoue**

Run: `cd front && npx vitest run src/test/contraste.test.ts`
Expected : FAIL — « bloc [data-theme="dark"] absent de index.css ».

- [ ] **Step 3: Réécrire `index.css`**

Remplacer `front/src/index.css` par :

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";

@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));

/* design-system/kaldera/MASTER.md — contrastes vérifiés par src/test/contraste.test.ts, dans les deux thèmes */
:root {
  color-scheme: light;
  --background: #F8FAFC;
  --foreground: #0F172A;
  --card: #FFFFFF;
  --card-foreground: #0F172A;
  --popover: #FFFFFF;
  --popover-foreground: #0F172A;
  --primary: #14532D;
  --primary-foreground: #FFFFFF;
  --secondary: #EEF2EC;
  --secondary-foreground: #14532D;
  --muted: #EEF2EC;
  --muted-foreground: #475569;
  --accent: #EEF2EC;
  --accent-foreground: #14532D;
  --destructive: #B91C1C;
  --border: #E2E8F0;
  --input: #E2E8F0;
  --ring: #A16207;
  --radius: 0.5rem;
  --or: #A16207;
  --or-sur-primaire: #FACC15;
  --ton-neutre: #475569;
  --ton-info: #1D4ED8;
  --ton-succes: #166534;
  --ton-attention: #854D0E;
  --ton-danger: #B91C1C;
}

[data-theme="dark"] {
  color-scheme: dark;
  --background: #0B1410;
  --foreground: #E6EEE9;
  --card: #111D17;
  --card-foreground: #E6EEE9;
  --popover: #111D17;
  --popover-foreground: #E6EEE9;
  --primary: #4ADE80;
  --primary-foreground: #052E16;
  --secondary: #1A2A21;
  --secondary-foreground: #E6EEE9;
  --muted: #1A2A21;
  --muted-foreground: #9AAFA3;
  --accent: #1A2A21;
  --accent-foreground: #E6EEE9;
  --destructive: #F87171;
  --border: #2A3B32;
  --input: #2A3B32;
  --ring: #FACC15;
  --or: #FACC15;
  --or-sur-primaire: #FACC15;
  --ton-neutre: #9AAFA3;
  --ton-info: #60A5FA;
  --ton-succes: #4ADE80;
  --ton-attention: #FBBF24;
  --ton-danger: #F87171;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --color-or: var(--or);
  --color-or-sur-primaire: var(--or-sur-primaire);
  --color-ton-neutre: var(--ton-neutre);
  --color-ton-info: var(--ton-info);
  --color-ton-succes: var(--ton-succes);
  --color-ton-attention: var(--ton-attention);
  --color-ton-danger: var(--ton-danger);
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) * 1.4);
  --radius-2xl: calc(var(--radius) * 1.8);
  --radius-3xl: calc(var(--radius) * 2.2);
  --radius-4xl: calc(var(--radius) * 2.6);
  --font-heading: var(--font-sans);
  --font-sans: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}

@layer base {
  * { @apply border-border outline-ring; }
  body { @apply bg-background text-foreground font-sans antialiased; }
  :focus-visible { outline: 3px solid var(--ring); outline-offset: 2px; }
  button, a, [role="button"] { cursor: pointer; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { transition: none !important; animation: none !important; }
  }
}
```

Dans `front/index.html`, remplacer le lien de police par :

```html
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />
```

- [ ] **Step 4: Vérifier**

Run: `cd front && npx vitest run src/test/contraste.test.ts && npm run build && npm run lint`
Expected : PASS (toutes les paires, deux thèmes, en-tête) ; build et lint sans erreur. Si une paire échoue, ajuster le token dans `index.css` **et** dans `MASTER.md`, puis consigner l'ajustement (Task 6, journal).

- [ ] **Step 5: Commit**

```bash
git add front/src/index.css front/src/test/contraste.test.ts front/index.html
git commit -m "feat(front): tokens clair / sombre du back-office, contraste AA vérifié par thème"
```

---

### Task 3: Thème mémorisé, système par défaut, sans flash

**Files:**
- Create: `front/src/theme.ts`, `front/src/useTheme.ts`
- Modify: `front/index.html` (script dans `<head>`)
- Test: `front/src/theme.test.ts`

**Interfaces:**
- Produces:
  - `type Theme = "clair" | "sombre"` ; `CLE_THEME = "kaldera.theme"`
  - `themeEnregistre(): Theme | null` · `themeSysteme(): Theme` · `appliquerTheme(theme: Theme): void` · `enregistrerTheme(theme: Theme): void`
  - `useTheme(): { theme: Theme; basculer: () => void }`

- [ ] **Step 1: Écrire les tests (rouges)**

Créer `front/src/theme.test.ts` :

```ts
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CLE_THEME, appliquerTheme, enregistrerTheme, themeEnregistre, themeSysteme } from "./theme";
import { useTheme } from "./useTheme";

type Ecouteur = (e: { matches: boolean }) => void;
let ecouteurs: Ecouteur[] = [];
const simulerSysteme = (sombre: boolean) => {
  ecouteurs = [];
  vi.stubGlobal("matchMedia", (requete: string) => ({
    matches: sombre && requete === "(prefers-color-scheme: dark)",
    media: requete,
    addEventListener: (_: string, f: Ecouteur) => ecouteurs.push(f),
    removeEventListener: (_: string, f: Ecouteur) => (ecouteurs = ecouteurs.filter((g) => g !== f)),
  }));
};

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  simulerSysteme(false);
});
afterEach(() => vi.unstubAllGlobals());

describe("theme.ts", () => {
  it("lit un choix valide, ignore un choix corrompu", () => {
    expect(themeEnregistre()).toBeNull();
    localStorage.setItem(CLE_THEME, "sombre");
    expect(themeEnregistre()).toBe("sombre");
    localStorage.setItem(CLE_THEME, "bleu");
    expect(themeEnregistre()).toBeNull();
  });

  it("suit le système", () => {
    expect(themeSysteme()).toBe("clair");
    simulerSysteme(true);
    expect(themeSysteme()).toBe("sombre");
  });

  it("applique data-theme sur <html>", () => {
    appliquerTheme("sombre");
    expect(document.documentElement.dataset.theme).toBe("dark");
    appliquerTheme("clair");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("survit à un localStorage indisponible", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("navigation privée");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("navigation privée");
    });
    expect(themeEnregistre()).toBeNull();
    expect(() => enregistrerTheme("sombre")).not.toThrow();
    vi.restoreAllMocks();
  });
});

describe("useTheme", () => {
  it("part du système sans choix enregistré et le suit en direct", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("clair");
    expect(document.documentElement.dataset.theme).toBe("light");
    act(() => ecouteurs.forEach((f) => f({ matches: true })));
    expect(result.current.theme).toBe("sombre");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("respecte le choix enregistré", () => {
    localStorage.setItem(CLE_THEME, "sombre");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("sombre");
  });

  it("basculer enregistre le choix, qui l'emporte ensuite sur le système", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.basculer());
    expect(result.current.theme).toBe("sombre");
    expect(localStorage.getItem(CLE_THEME)).toBe("sombre");
    act(() => ecouteurs.forEach((f) => f({ matches: false })));
    expect(result.current.theme).toBe("sombre");
  });

  it("bascule quand même si localStorage est indisponible", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("navigation privée");
    });
    const { result } = renderHook(() => useTheme());
    act(() => result.current.basculer());
    expect(result.current.theme).toBe("sombre");
    vi.restoreAllMocks();
  });
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `cd front && npx vitest run src/theme.test.ts`
Expected : FAIL — modules `./theme` et `./useTheme` introuvables.

- [ ] **Step 3: Implémenter `theme.ts` et `useTheme.ts`**

`front/src/theme.ts` :

```ts
export type Theme = "clair" | "sombre";

export const CLE_THEME = "kaldera.theme";
const REQUETE_SOMBRE = "(prefers-color-scheme: dark)";

/** Choix explicite de l'utilisateur, ou null (absent, corrompu, ou stockage indisponible). */
export function themeEnregistre(): Theme | null {
  try {
    const valeur = localStorage.getItem(CLE_THEME);
    return valeur === "clair" || valeur === "sombre" ? valeur : null;
  } catch {
    return null;
  }
}

export function themeSysteme(): Theme {
  return window.matchMedia?.(REQUETE_SOMBRE).matches ? "sombre" : "clair";
}

export function appliquerTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme === "sombre" ? "dark" : "light";
}

export function enregistrerTheme(theme: Theme): void {
  try {
    localStorage.setItem(CLE_THEME, theme);
  } catch {
    // navigation privée : le choix vaut pour la session seulement
  }
}

export function ecouterSysteme(rappel: (theme: Theme) => void): () => void {
  const requete = window.matchMedia?.(REQUETE_SOMBRE);
  if (!requete) return () => {};
  const surChangement = (e: { matches: boolean }) => rappel(e.matches ? "sombre" : "clair");
  requete.addEventListener("change", surChangement);
  return () => requete.removeEventListener("change", surChangement);
}
```

`front/src/useTheme.ts` :

```ts
import { useEffect, useState } from "react";
import { type Theme, appliquerTheme, ecouterSysteme, enregistrerTheme, themeEnregistre, themeSysteme } from "./theme";

export function useTheme(): { theme: Theme; basculer: () => void } {
  const [theme, setTheme] = useState<Theme>(() => themeEnregistre() ?? themeSysteme());
  const [choisi, setChoisi] = useState(() => themeEnregistre() !== null);

  useEffect(() => appliquerTheme(theme), [theme]);
  useEffect(() => (choisi ? undefined : ecouterSysteme(setTheme)), [choisi]);

  const basculer = () => {
    const suivant: Theme = theme === "sombre" ? "clair" : "sombre";
    enregistrerTheme(suivant);
    setChoisi(true);
    setTheme(suivant);
  };
  return { theme, basculer };
}
```

- [ ] **Step 4: Script sans flash dans `index.html`**

Dans `front/index.html`, juste après `<title>…</title>`, ajouter :

```html
    <script>
      // Thème avant le premier rendu (pas de flash) ; même règle que src/theme.ts.
      (function () {
        var choix = null;
        try { choix = localStorage.getItem("kaldera.theme"); } catch (e) {}
        var sombre = choix === "sombre" ||
          (choix !== "clair" && !!window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
        document.documentElement.dataset.theme = sombre ? "dark" : "light";
      })();
    </script>
```

- [ ] **Step 5: Vérifier**

Run: `cd front && npx vitest run src/theme.test.ts && npm run lint && npm run build`
Expected : 8 tests PASS ; lint et build propres.

- [ ] **Step 6: Commit**

```bash
git add front/src/theme.ts front/src/useTheme.ts front/src/theme.test.ts front/index.html
git commit -m "feat(front): thème clair / sombre mémorisé, système par défaut, sans flash"
```

---

### Task 4: Composant `Statut` et catalogue des statuts

**Files:**
- Create: `front/src/statuts.ts`, `front/src/components/Statut.tsx`
- Test: `front/src/components/Statut.test.tsx`

**Interfaces:**
- Consumes: classes `text-ton-*` (Task 2) ; `cn` de `@/lib/utils`.
- Produces: `type Ton = "neutre" | "info" | "succes" | "attention" | "danger"` ; `STATUTS: Record<string, { libelle: string; icone: LucideIcon; ton: Ton }>` ; `<Statut code: string />`.

- [ ] **Step 1: Écrire les tests (rouges)**

Créer `front/src/components/Statut.test.tsx` :

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";
import { STATUTS } from "@/statuts";
import { Statut } from "./Statut";

describe("Statut", () => {
  it.each(Object.entries(STATUTS))("%s : icône décorative, libellé et ton", (code, { libelle, ton }) => {
    const { container } = render(<Statut code={code} />);
    const badge = screen.getByText(libelle);
    expect(badge).toHaveClass(`text-ton-${ton}`);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("couvre tout le vocabulaire du brief", () => {
    expect(Object.keys(STATUTS).sort()).toEqual(
      [
        "admission", "en_cours", "terminee", "secours",
        "acceptee", "refusee", "escalade",
        "en_attente", "termine", "sautee", "echec", "repli", "degrade",
        "mode_degrade", "borne",
      ].sort(),
    );
  });

  it.each(["inconnu", "constructor", "toString", ""])("code hors catalogue %j : neutre, code brut", (code) => {
    render(<Statut code={code} />);
    const badge = screen.getByTestId("statut");
    expect(badge).toHaveClass("text-ton-neutre");
    expect(badge).toHaveTextContent(code);
  });

  it("n'a aucune violation axe", async () => {
    const { container } = render(
      <ul>
        {Object.keys(STATUTS).map((code) => (
          <li key={code}><Statut code={code} /></li>
        ))}
      </ul>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `cd front && npx vitest run src/components/Statut.test.tsx`
Expected : FAIL — `@/statuts` et `./Statut` introuvables.

- [ ] **Step 3: Implémenter le catalogue et le composant**

`front/src/statuts.ts` :

```ts
import {
  CircleCheck, CircleX, Clock, FileSearch, LifeBuoy, Loader, OctagonX, RotateCcw, SkipForward, UserRound,
  type LucideIcon,
} from "lucide-react";

export type Ton = "neutre" | "info" | "succes" | "attention" | "danger";
export type DefinitionStatut = { libelle: string; icone: LucideIcon; ton: Ton };

/** Codes du back-end (demandes.statut, Issue, étapes de la machine) ; spec C3-1 §3.4. */
export const STATUTS: Record<string, DefinitionStatut> = {
  // demande
  admission: { libelle: "En analyse", icone: FileSearch, ton: "info" },
  en_cours: { libelle: "En traitement", icone: Loader, ton: "info" },
  terminee: { libelle: "Terminée", icone: CircleCheck, ton: "succes" },
  secours: { libelle: "Fiche de secours", icone: LifeBuoy, ton: "attention" },
  // issue
  acceptee: { libelle: "Acceptée", icone: CircleCheck, ton: "succes" },
  refusee: { libelle: "Refusée", icone: CircleX, ton: "danger" },
  escalade: { libelle: "Escaladée", icone: UserRound, ton: "attention" },
  // étape (en_cours : même code que la demande)
  en_attente: { libelle: "En attente", icone: Clock, ton: "neutre" },
  termine: { libelle: "Terminée", icone: CircleCheck, ton: "succes" },
  sautee: { libelle: "Sautée", icone: SkipForward, ton: "neutre" },
  echec: { libelle: "Échec", icone: CircleX, ton: "danger" },
  repli: { libelle: "Repli déterministe", icone: RotateCcw, ton: "attention" },
  degrade: { libelle: "Mode dégradé", icone: LifeBuoy, ton: "attention" },
  // badges
  mode_degrade: { libelle: "Mode dégradé", icone: LifeBuoy, ton: "attention" },
  borne: { libelle: "Borne atteinte", icone: OctagonX, ton: "danger" },
};
```

Note : la spec (§3.4) donne « En traitement » pour `en_cours` (demande) et « En cours » pour l'étape, tout en imposant un seul code au même rendu ; décision du plan : un seul libellé, « En traitement », valable pour les deux.

`front/src/components/Statut.tsx` :

```tsx
import { Circle } from "lucide-react";
import { cn } from "@/lib/utils";
import { STATUTS, type Ton } from "@/statuts";

const COULEURS: Record<Ton, string> = {
  neutre: "text-ton-neutre",
  info: "text-ton-info",
  succes: "text-ton-succes",
  attention: "text-ton-attention",
  danger: "text-ton-danger",
};

/** Icône + libellé + couleur ; un code hors catalogue s'affiche brut, en neutre. */
export function Statut({ code }: { code: string }) {
  const definition = Object.hasOwn(STATUTS, code) ? STATUTS[code] : undefined;
  const Icone = definition?.icone ?? Circle;
  return (
    <span
      data-testid="statut"
      className={cn("inline-flex items-center gap-1 text-sm font-medium", COULEURS[definition?.ton ?? "neutre"])}
    >
      <Icone aria-hidden="true" className="size-4 shrink-0" />
      {definition?.libelle ?? code}
    </span>
  );
}
```

- [ ] **Step 4: Vérifier**

Run: `cd front && npx vitest run src/components/Statut.test.tsx && npm run lint && npm run build`
Expected : PASS (15 codes + vocabulaire + 4 codes hors catalogue + axe) ; lint et build propres.

- [ ] **Step 5: Commit**

```bash
git add front/src/statuts.ts front/src/components/Statut.tsx front/src/components/Statut.test.tsx
git commit -m "feat(front): composant Statut (icône + libellé + couleur) et catalogue des statuts"
```

---

### Task 5: Coquille, routes E1 / E2 / E3 / 404 et test de fumée

**Files:**
- Create: `front/src/components/Coquille.tsx`, `front/src/pages.tsx`
- Modify: `front/src/App.tsx`, `front/src/App.test.tsx`, `front/e2e/fumee.spec.ts`

**Interfaces:**
- Consumes: `useTheme()` (Task 3) ; `Button` de `@/components/ui/button` ; classes de la Task 2.
- Produces: `export function Routage()` (les `<Routes>`, testable sous `MemoryRouter`) ; `export default function App()` (= `BrowserRouter` + `Routage`) ; pages `ListeDemandes`, `Dossier`, `Lot`, `Introuvable` ; `Coquille`.

- [ ] **Step 1: Écrire les tests (rouges)**

Remplacer `front/src/App.test.tsx` par :

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import { Routage } from "./App";

const ouvrir = (chemin: string) =>
  render(
    <MemoryRouter initialEntries={[chemin]}>
      <Routage />
    </MemoryRouter>,
  );

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
});

describe("socle", () => {
  it.each([
    ["/", "Liste des demandes"],
    ["/demandes/KAL-26-0101", "Dossier KAL-26-0101"],
    ["/lots/1", "Lot 1"],
    ["/nulle-part", "Page introuvable"],
  ])("%s affiche son titre", (chemin, titre) => {
    ouvrir(chemin);
    expect(screen.getByRole("heading", { level: 1, name: titre })).toBeInTheDocument();
    expect(document.title).toBe(`Kaldera · ${titre}`);
  });

  it("la 404 ramène à la liste", () => {
    ouvrir("/nulle-part");
    expect(screen.getByRole("link", { name: "Retour à la liste des demandes" })).toHaveAttribute("href", "/");
  });

  it("en-tête : marque, lien Demandes courant, lien d'évitement en premier", async () => {
    ouvrir("/");
    expect(screen.getByText("Kaldera · back-office gestionnaire")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Demandes" })).toHaveAttribute("aria-current", "page");
    await userEvent.tab();
    expect(screen.getByRole("link", { name: "Aller au contenu" })).toHaveFocus();
  });

  it("le bouton de thème bascule et change son libellé", async () => {
    ouvrir("/");
    await userEvent.click(screen.getByRole("button", { name: "Passer au thème sombre" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("button", { name: "Passer au thème clair" })).toBeInTheDocument();
  });

  it("n'a aucune violation axe", async () => {
    const { container } = ouvrir("/");
    expect(await axe(container)).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Vérifier qu'ils échouent**

Run: `cd front && npx vitest run src/App.test.tsx`
Expected : FAIL — `Routage` n'est pas exporté par `./App`.

- [ ] **Step 3: Pages cadres**

`front/src/pages.tsx` :

```tsx
import { type ReactNode, useEffect } from "react";
import { Link, useParams } from "react-router-dom";

function Cadre({ titre, children }: { titre: string; children: ReactNode }) {
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

const Vide = ({ children }: { children: ReactNode }) => (
  <p className="rounded-lg border border-dashed p-6 text-muted-foreground">{children}</p>
);

export function ListeDemandes() {
  return (
    <Cadre titre="Liste des demandes">
      <Vide>Écran livré au sous-projet C3-2 : liste filtrable des demandes et sélection pour traitement.</Vide>
    </Cadre>
  );
}

export function Dossier() {
  const { reference = "" } = useParams();
  return (
    <Cadre titre={`Dossier ${reference}`}>
      <Vide>Écran livré au sous-projet C3-2 : timeline des agents, garanties et carte anti-fraude.</Vide>
    </Cadre>
  );
}

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
```

- [ ] **Step 4: Coquille**

`front/src/components/Coquille.tsx` :

```tsx
import { Moon, Sun } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/useTheme";

// Dans l'en-tête vert (clair), l'anneau or foncé ne tient pas 3:1 : on prend l'or clair.
// Le lien utilise outline, le Button shadcn utilise ring : les deux sont surchargés.
const FOCUS_ENTETE =
  "focus-visible:outline-or-sur-primaire focus-visible:ring-or-sur-primaire dark:focus-visible:outline-ring dark:focus-visible:ring-ring";

export function Coquille() {
  const { theme, basculer } = useTheme();
  const sombre = theme === "sombre";
  return (
    <>
      <a
        href="#contenu"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-foreground"
      >
        Aller au contenu
      </a>
      <header className="border-b bg-primary text-primary-foreground dark:bg-card dark:text-foreground">
        <div className="mx-auto flex h-12 max-w-[1440px] items-center gap-6 px-4">
          <span className="font-semibold">Kaldera · back-office gestionnaire</span>
          <nav aria-label="Navigation principale">
            <NavLink
              to="/"
              end
              className={`rounded-sm px-1 underline-offset-4 hover:underline aria-[current=page]:underline aria-[current=page]:decoration-or-sur-primaire dark:aria-[current=page]:decoration-or ${FOCUS_ENTETE}`}
            >
              Demandes
            </NavLink>
          </nav>
          <Button
            variant="ghost"
            size="icon"
            className={`ml-auto text-inherit ${FOCUS_ENTETE}`}
            aria-label={sombre ? "Passer au thème clair" : "Passer au thème sombre"}
            onClick={basculer}
          >
            {sombre ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
          </Button>
        </div>
      </header>
      <main id="contenu" tabIndex={-1} className="mx-auto max-w-[1440px] px-4 py-4 outline-none">
        <Outlet />
      </main>
    </>
  );
}
```

- [ ] **Step 5: `App.tsx`**

Remplacer `front/src/App.tsx` par :

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Coquille } from "./components/Coquille";
import { Dossier, Introuvable, ListeDemandes, Lot } from "./pages";

export function Routage() {
  return (
    <Routes>
      <Route element={<Coquille />}>
        <Route path="/" element={<ListeDemandes />} />
        <Route path="/demandes/:reference" element={<Dossier />} />
        <Route path="/lots/:id" element={<Lot />} />
        <Route path="*" element={<Introuvable />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routage />
    </BrowserRouter>
  );
}
```

- [ ] **Step 6: Vérifier les tests unitaires**

Run: `cd front && npm test && npm run lint && npm run build`
Expected : toutes les suites PASS (contraste, thème, Statut, App, format) ; lint et build propres. Si `oxlint` signale `react/only-export-components` sur `App.tsx` (deux exports), garder les deux exports et le justifier dans le rapport (le test a besoin de `Routage`).

- [ ] **Step 7: Test de fumée Playwright**

Remplacer `front/e2e/fumee.spec.ts` par :

```ts
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const sansViolation = async (page: Page) =>
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
const theme = (page: Page) => page.evaluate(() => document.documentElement.dataset.theme);

test("E1, thème mémorisé sans flash, axe dans les deux thèmes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Liste des demandes" })).toBeVisible();
  expect(await theme(page)).toBe("light");
  await sansViolation(page);

  await page.getByRole("button", { name: "Passer au thème sombre" }).click();
  expect(await theme(page)).toBe("dark");
  await sansViolation(page);

  await page.reload({ waitUntil: "domcontentloaded" });
  expect(await theme(page)).toBe("dark"); // posé par le script de index.html, avant React
  await expect(page.getByRole("button", { name: "Passer au thème clair" })).toBeVisible();
});

test("sans choix enregistré, le thème suit le système", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  expect(await theme(page)).toBe("dark");
});

test("clavier : lien d'évitement, Demandes, bouton de thème", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Aller au contenu" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Demandes" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: /Passer au thème/ })).toBeFocused();
});
```

Run (depuis la racine du dépôt) : `make front-e2e`
Expected : 3 tests × 2 projets (mobile, desktop) PASS.

- [ ] **Step 8: Commit**

```bash
git add front/src/App.tsx front/src/App.test.tsx front/src/pages.tsx front/src/components/Coquille.tsx front/e2e/fumee.spec.ts
git commit -m "feat(front): socle du back-office (coquille, routes E1 / E2 / E3 / 404, bouton de thème)"
```

---

### Task 6: Cahier de recette, README, captures

**Files:**
- Modify: `docs/recette/generer_cahier_recette.py`, `docs/recette/cahier-recette.pdf` (régénéré)
- Modify: `README.md`
- Create: `docs/captures/ihm-clair.png`, `docs/captures/ihm-sombre.png`
- Modify (seulement si un token a été ajusté en Task 2) : `docs/journal_ajustements.md`

- [ ] **Step 1: Cahier de recette**

Dans `docs/recette/generer_cahier_recette.py` :
- S-04, résultat attendu : `"Vite sert le back-office gestionnaire sur http://localhost:5173."`
- Remplacer la liste `UI = [...]` par :

```python
UI = [
    ("Socle du back-office", [
        ("U-01", "Ouvrir <b>http://localhost:5173</b>.",
         "En-tête « Kaldera · back-office gestionnaire », lien « Demandes » souligné (page "
         "courante), bouton de thème ; titre « Liste des demandes » et cadre « Écran livré au "
         "sous-projet C3-2 »."),
        ("U-02", "Cliquer le bouton de thème (lune), recharger la page, puis recliquer (soleil).",
         "Passage en sombre ; après rechargement la page reste en sombre, sans flash clair ; "
         "second clic : retour en clair. Navigateur sans choix enregistré (fenêtre privée) : "
         "la page suit le thème du système."),
        ("U-03", "Recharger, puis appuyer sur Tab trois fois.",
         "1er Tab : « Aller au contenu » apparaît en haut à gauche ; 2e : « Demandes » ; 3e : "
         "bouton de thème. Anneau de focus or visible à chaque fois, dans les deux thèmes."),
        ("U-04", "Ouvrir <i>/demandes/KAL-26-0101</i>, <i>/lots/1</i>, puis <i>/inconnu</i>.",
         "Titres « Dossier KAL-26-0101 » et « Lot 1 » (cadres C3-2 / C3-3) ; adresse inconnue : "
         "« Page introuvable » et lien « Retour à la liste des demandes »."),
    ]),
]
```

- Légende : `"<b>S-01 à S-05</b>, puis <b>U-01</b>, puis <b>A-01 à A-04</b>."` → `"<b>S-01 à S-05</b>, puis <b>U-01 à U-04</b>, puis <b>A-01 à A-04</b>."`
- Introduction de la section 2 : `"Navigateur sur http://localhost:5173. Le socle du back-office (C3-1) est livré ; les écrans E1, E2, E3 (EX-D44 → EX-D50) s'ajoutent avec les sous-projets C3-2 à C3-4."`
- « Version testée » : branche `feature/chantier3-c3-1-design-system` ; « Durée estimée » : `"20 minutes environ"`.
- `STATUTS` : retirer `"U-01": "OK"` (statuts U-01 → U-04 renseignés en Task 8 après déroulé).

Run: `uv run python docs/recette/generer_cahier_recette.py`

- [ ] **Step 2: Captures**

```bash
mkdir -p docs/captures && cd front
npx vite --port 5173 --strictPort > /tmp/vite-c3-1.log 2>&1 & VITE_PID=$!
sleep 4
npx playwright screenshot --color-scheme=light --viewport-size=1280,720 http://localhost:5173 ../docs/captures/ihm-clair.png
npx playwright screenshot --color-scheme=dark --viewport-size=1280,720 http://localhost:5173 ../docs/captures/ihm-sombre.png
kill "$VITE_PID"
cd ..
```

(Arrêter uniquement le serveur Vite lancé ici, par son PID ; si le port 5173 est déjà pris, le signaler au lieu de tuer un processus étranger. Vérifier `ls -la docs/captures`.)

- [ ] **Step 3: README**

Remplacer le bloc commençant par `IHM (back-office gestionnaire, chantier 3 en cours) :` jusqu'au bloc de code inclus par :

````markdown
IHM : back-office gestionnaire (chantier 3 ; socle livré en C3-1, écrans E1 / E2 / E3 à venir) :

```bash
make up
docker compose --profile integration up -d --wait postgres
make demo    # demande KAL-26-0101 et son contrat
make api     # http://127.0.0.1:8000/docs
make worker
make front   # http://localhost:5173 : back-office gestionnaire
```

Thème clair / sombre : bouton en haut à droite, choix mémorisé dans le navigateur (`kaldera.theme`) ;
sans choix, le thème du système. Design system : `design-system/kaldera/MASTER.md` (généré avec
`ui-ux-pro-max`, tokens et contrastes) et `design-system/kaldera/pages/back-office.md`.

| Clair | Sombre |
|---|---|
| ![IHM en thème clair](docs/captures/ihm-clair.png) | ![IHM en thème sombre](docs/captures/ihm-sombre.png) |
````

Et dans la ligne `make front-e2e` : `# Playwright : socle du back-office (thème, clavier, axe ; démarre PostgreSQL de test)`.

- [ ] **Step 4: Journal (conditionnel)**

Si et seulement si un token a été ajusté en Task 2 : ajouter une ligne datée au premier tableau de `docs/journal_ajustements.md` (scénario `contraste.test.ts`, signal = paire et ratio mesuré, seuil AA, ajustement = ancienne → nouvelle valeur).

- [ ] **Step 5: Vérifier et committer**

Run: `.venv/bin/python -I -c "from pypdf import PdfReader; t=' '.join(p.extract_text() for p in PdfReader('docs/recette/cahier-recette.pdf').pages); print([m for m in ['U-04','Aller au contenu','Page introuvable'] if m not in t] or 'OK')"`
Expected : `OK`.

```bash
git add docs/recette README.md docs/captures docs/journal_ajustements.md
git commit -m "docs: cahier de recette U-01 → U-04, README et captures du socle du back-office"
```

---

### Task 7: Dossier de conception — page design system

**Files:**
- Create: `docs/conception/pages/298-ihm-design-system.html`
- Modify: `docs/conception/pages/020-sommaire.html`, `docs/conception/pages/440-glossaire-5.html`
- Regenerate: `docs/conception/dossier-conception.pdf` (ignoré par git) → copie `../../dossier-conception.pdf`

- [ ] **Step 1: Nouvelle page**

Créer `docs/conception/pages/298-ihm-design-system.html` sur le modèle de `290-verite-terrain.html` (`<section class="page" id="ihm-design-system">`, `surtitre`, `h2.titre` avec `<span class="num">2.8</span>`, `chapo`, `tableau`, `grille-2` / `grille-3`, `note`) :
- surtitre « Livrable 2 · IHM gestionnaire » ; titre « 2.8 🎨 IHM gestionnaire · design system » ;
- chapo : back-office local des gestionnaires (EX-D44, EX-D51), design system produit avec `ui-ux-pro-max` (profil Data-Dense Dashboard), thème clair / sombre ;
- tableau « Écarts avec la recommandation `ui-ux-pro-max` » (3 lignes du §2.2 de la spec + anneau de focus de l'en-tête) ;
- tableau « Tokens » : rôle · clair · sombre · contraste sur carte (lignes du §2.2) ; pastilles de couleur (`<span style="display:inline-block;width:10px;height:10px;background:#…">`) ;
- tableau « Statuts » : famille · code · libellé · ton (§3.4) ;
- `grille-3` de notes : « Thème » (clé `kaldera.theme`, système par défaut, script avant rendu), « Accessibilité » (AA vérifié par test dans les deux thèmes, focus or, lien d'évitement), « Socle » (routes E1 / E2 / E3 / 404 ; écrans en C3-2 et C3-3).

Ne pas citer l'espace assuré (critère du dossier depuis C3-0).

- [ ] **Step 2: Sommaire et glossaire**

- `020-sommaire.html`, entrée 2 : ajouter après « générateur de pièces (2.7) » : ` · <span class="neuf">IHM gestionnaire : design system (2.8)</span>` ; chapo : « Version alignée sur le code (chantier 3, sous-projet C3-1). »
- `440-glossaire-5.html` : chapo « Les termes liés à la liaison A2A, à la mesure (chantier 2) et à l'IHM gestionnaire (chantier 3). » ; ajouter trois lignes au tableau :
  - « Design system » — Règles visuelles communes (couleurs, typographie, composants, états) du back-office, dans `design-system/kaldera/` ; produit avec `ui-ux-pro-max`.
  - « Token de design » — Variable CSS nommée (`--primary`, `--ton-danger`…) définie une fois par thème ; les écrans n'utilisent jamais une couleur en dur.
  - « Thème clair / sombre » — Jeu de tokens choisi par l'attribut `data-theme` ; défaut : thème du système ; choix mémorisé (`kaldera.theme`).

- [ ] **Step 3: Rendre, contrôler, copier**

Run: `make dossier`
Expected : « 47 fragments → …/dossier-conception.pdf », aucun avertissement de débordement (sinon raccourcir le texte, jamais la police).

```bash
cp docs/conception/dossier-conception.pdf ../../dossier-conception.pdf
.venv/bin/python -I -c "import re; from pypdf import PdfReader; r=PdfReader('../../dossier-conception.pdf'); t=' '.join(p.extract_text() or '' for p in r.pages); print(len(r.pages), 'pages', 'design system' in t.lower(), re.findall(r'espace assur|agent de relance|UI1', t, re.I) or 'OK')"
```

Expected : `47 pages True OK`.

- [ ] **Step 4: Commit**

```bash
git add docs/conception/pages
git commit -m "docs(conception): page 2.8 IHM gestionnaire — design system, sommaire et glossaire"
```

---

### Task 8: Vérification finale et déroulé de la recette

**Files:**
- Modify: `docs/recette/generer_cahier_recette.py` (`STATUTS`), `docs/recette/cahier-recette.pdf`

- [ ] **Step 1: Toutes les suites**

Run: `make test && make lint && make typecheck && make test-integration`
Expected : vert (back-end inchangé).

Run: `cd front && npm test && npm run lint && npm run build && cd .. && make front-e2e`
Expected : vert.

- [ ] **Step 2: Aucune régression de vocabulaire**

Run: `grep -rn -E 'a-refaire|\.dark\b|next-themes|bg-\[#|text-\[#' front/src front/index.html`
Expected : aucune sortie (pas de jeton UI1, pas de variante `.dark`, pas de couleur en dur).

- [ ] **Step 3: Dérouler la recette**

Suivre `docs/recette/cahier-recette.pdf` : S-01 → S-05, U-01 → U-04, A-01 → A-04 (`KALDERA_DATABASE_URL=postgresql://kaldera:kaldera@localhost:5433/kaldera_test` en ligne de commande si aucun `.env` ; ne jamais créer de `.env`). Sans profil VLM Azure, S-03 est `NT` (motif : « pas de profil VLM Azure sur ce poste »). U-01 → U-04 : navigateur headless (Playwright) contre `make front`, en vérifiant chaque résultat attendu du cas (h1, libellés, `data-theme`, ordre du focus, 404). Arrêter tout processus lancé ; terminer par `make recette-reset`.

- [ ] **Step 4: Renseigner et régénérer**

Dans `STATUTS`, ajouter les statuts relevés pour U-01 → U-04 (et mettre à jour S-01 → A-04 selon le déroulé), puis :

Run: `uv run python docs/recette/generer_cahier_recette.py`

- [ ] **Step 5: Commit**

```bash
git add docs/recette/generer_cahier_recette.py docs/recette/cahier-recette.pdf
git commit -m "docs(recette): statuts du déroulé C3-1"
```

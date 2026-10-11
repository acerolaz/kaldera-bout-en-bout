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

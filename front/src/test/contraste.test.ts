import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(path.resolve(process.cwd(), "src/index.css"), "utf-8"); // cwd = front/
const jeton = (nom: string): string => {
  const m = css.match(new RegExp(`--${nom}:\\s*(#[0-9A-Fa-f]{6})`));
  if (!m) throw new Error(`jeton --${nom} absent de index.css`);
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

describe("contrastes du design system (WCAG AA)", () => {
  it.each([
    ["foreground", "background", 4.5],
    ["primary-foreground", "primary", 4.5],
    ["muted-foreground", "background", 4.5],
    ["destructive", "card", 4.5],
    ["succes", "card", 4.5],
    ["a-refaire", "card", 4.5],
    ["or-sur-primaire", "primary", 4.5],
    ["ring", "background", 3],
    ["or", "card", 3],
  ])("%s sur %s ≥ %s:1", (texte, fond, seuil) => {
    expect(contraste(jeton(texte), jeton(fond))).toBeGreaterThanOrEqual(seuil);
  });
});

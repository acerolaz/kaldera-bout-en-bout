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

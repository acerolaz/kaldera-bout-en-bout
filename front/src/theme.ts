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

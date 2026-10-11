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

import { Moon, Sun } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/useTheme";

// Dans l'en-tête vert (clair), l'anneau or foncé ne tient pas 3:1 : on prend l'or clair.
// Le lien utilise outline, le Button shadcn utilise ring : les deux sont surchargés.
const FOCUS_ENTETE =
  "focus-visible:outline-or-sur-primaire focus-visible:ring-or-sur-primaire dark:focus-visible:outline-ring dark:focus-visible:ring-ring focus-visible:border-or-sur-primaire dark:focus-visible:border-ring";

export function Coquille() {
  const { theme, basculer } = useTheme();
  const sombre = theme === "sombre";
  return (
    <>
      <a
        href="#contenu"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-foreground focus-visible:outline-or-sur-primaire dark:focus-visible:outline-ring"
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

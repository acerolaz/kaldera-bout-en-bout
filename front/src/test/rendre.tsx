import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { vi } from "vitest";

// Sonde de test : ce module n'est jamais rechargé à chaud.
// eslint-disable-next-line react-refresh/only-export-components
function SondeUrl() {
  const { pathname, search } = useLocation();
  return <span hidden data-testid="url">{pathname + search}</span>;
}

/** Rend un élément avec un QueryClient neuf (sans réessai) et un routeur en mémoire. */
export function rendre(element: ReactElement, chemin = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[chemin]}>
        {element}
        <SondeUrl />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export const json = (corps: unknown, statut = 200): Response =>
  new Response(JSON.stringify(corps), { status: statut, headers: { "Content-Type": "application/json" } });

/** Remplace fetch ; le gestionnaire reçoit l'URL demandée (ex. "/api/demandes?issue=escalade") et l'init (POST). */
export function simulerApi(gestionnaire: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const espion = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => gestionnaire(String(url), init));
  vi.stubGlobal("fetch", espion);
  return espion;
}

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ErreurApi } from "./api";
import { Coquille } from "./components/Coquille";
import { Dossier } from "./pages/Dossier";
import { ListeDemandes } from "./pages/ListeDemandes";
import { Lot } from "./pages/Lot";
import { Introuvable } from "./pages/socle";

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

// une réponse HTTP (404, API arrêtée derrière le proxy) s'affiche tout de suite ; seule une coupure réseau est relancée
const reessayer = (echecs: number, erreur: Error) => !(erreur instanceof ErreurApi) && echecs < 1;

export default function App() {
  // un client par application, pas de global de module
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: reessayer } } }));
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Routage />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Coquille } from "./components/Coquille";
import { Dossier } from "./pages/Dossier";
import { ListeDemandes } from "./pages/ListeDemandes";
import { Introuvable, Lot } from "./pages/socle";

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
  const [client] = useState(() => new QueryClient()); // un client par application, pas de global de module
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Routage />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

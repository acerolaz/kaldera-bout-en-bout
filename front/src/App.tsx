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

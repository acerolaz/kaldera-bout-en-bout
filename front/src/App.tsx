import { BrowserRouter, Route, Routes, useParams } from "react-router-dom";
import { Toaster } from "sonner";
import { Connexion } from "./pages/Connexion";
import { MesSinistres } from "./pages/MesSinistres";
import { Sinistre } from "./pages/Sinistre";

function PageSinistre() {
  const { reference = "" } = useParams();
  return <Sinistre reference={reference} />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/connexion" element={<Connexion />} />
        <Route path="/" element={<MesSinistres />} />
        <Route path="/sinistres/:reference" element={<PageSinistre />} />
      </Routes>
      <Toaster richColors position="top-center" />
    </BrowserRouter>
  );
}

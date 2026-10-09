import { BrowserRouter, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { Toaster } from "sonner";
import { Chat } from "./components/Chat";
import { Connexion } from "./pages/Connexion";
import { MesSinistres } from "./pages/MesSinistres";
import { Sinistre } from "./pages/Sinistre";

function PageSinistre() {
  const { reference = "" } = useParams();
  const naviguer = useNavigate();
  return (
    <Sinistre
      reference={reference}
      chat={({ messages, deposer }) => (
        <Chat
          reference={reference}
          messages={messages}
          onDeposer={deposer}
          onExpire={() => naviguer("/connexion", { replace: true })}
        />
      )}
    />
  );
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

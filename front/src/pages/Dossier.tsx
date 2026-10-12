import { useParams } from "react-router-dom";
import { Cadre } from "./socle";

export function Dossier() {
  const { reference = "" } = useParams();
  return <Cadre titre={`Dossier ${reference}`}>{null}</Cadre>;
}

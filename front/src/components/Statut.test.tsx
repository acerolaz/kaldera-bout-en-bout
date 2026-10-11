import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";
import { STATUTS } from "@/statuts";
import { Statut } from "./Statut";

describe("Statut", () => {
  it.each(Object.entries(STATUTS))("%s : icône décorative, libellé et ton", (code, { libelle, ton }) => {
    const { container } = render(<Statut code={code} />);
    const badge = screen.getByText(libelle);
    expect(badge).toHaveClass(`text-ton-${ton}`);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("couvre tout le vocabulaire du brief", () => {
    expect(Object.keys(STATUTS).sort()).toEqual(
      [
        "admission", "en_cours", "terminee", "secours",
        "acceptee", "refusee", "escalade",
        "en_attente", "termine", "sautee", "echec", "repli", "degrade",
        "mode_degrade", "borne",
      ].sort(),
    );
  });

  it.each(["inconnu", "constructor", "toString", ""])("code hors catalogue %j : neutre, code brut", (code) => {
    render(<Statut code={code} />);
    const badge = screen.getByTestId("statut");
    expect(badge).toHaveClass("text-ton-neutre");
    expect(badge).toHaveTextContent(code);
  });

  it("n'a aucune violation axe", async () => {
    const { container } = render(
      <ul>
        {Object.keys(STATUTS).map((code) => (
          <li key={code}><Statut code={code} /></li>
        ))}
      </ul>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});

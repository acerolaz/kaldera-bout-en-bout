import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { axe } from "vitest-axe";
import App from "./App";

it("affiche la page d'attente du back-office, sans violation axe", async () => {
  const { container } = render(<App />);
  expect(
    screen.getByRole("heading", { level: 1, name: "Kaldera · back-office gestionnaire" }),
  ).toBeInTheDocument();
  expect(screen.getByText("En construction (chantier 3).")).toBeInTheDocument();
  expect(await axe(container)).toHaveNoViolations();
});

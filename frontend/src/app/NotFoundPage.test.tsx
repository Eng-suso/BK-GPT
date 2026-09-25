import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { i18n } from "@/lib/i18n";

import { NotFoundPage } from "./NotFoundPage";

describe("NotFoundPage", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("it");
  });

  it("dice che l'indirizzo non porta da nessuna parte, e quale", () => {
    render(
      <MemoryRouter initialEntries={["/projects/p-sparito/processes/x"]}>
        <NotFoundPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("Questa pagina non esiste")).toBeInTheDocument();
    // L'indirizzo in chiaro serve: spesso e' un link vecchio che qualcuno ha
    // mandato, e chi lo legge deve capire quale.
    expect(
      screen.getByText(/\/projects\/p-sparito\/processes\/x/),
    ).toBeInTheDocument();
  });

  it("offre una via di uscita invece di lasciare fermi", () => {
    render(
      <MemoryRouter initialEntries={["/rotto"]}>
        <NotFoundPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: "Vai agli incarichi" })).toBeInTheDocument();
  });
});

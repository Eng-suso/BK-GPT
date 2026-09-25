import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { i18n } from "@/lib/i18n";

import { ErrorBoundary } from "./ErrorBoundary";

function Explodes(): React.JSX.Element {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("it");
    // React stampa l'errore catturato: nel test e' rumore atteso, non un guasto.
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("mostra cosa e' successo invece di lasciare la pagina vuota", () => {
    render(
      <ErrorBoundary>
        <Explodes />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Questa schermata si è fermata")).toBeInTheDocument();
  });

  it("tiene in piedi quello che sta fuori dalla schermata rotta", () => {
    render(
      <div>
        <nav>Navigazione</nav>
        <ErrorBoundary>
          <Explodes />
        </ErrorBoundary>
      </div>,
    );

    // Il difetto era proprio questo: senza rete, l'albero React si smontava
    // tutto e spariva anche la navigazione.
    expect(screen.getByText("Navigazione")).toBeInTheDocument();
  });

  it("riprova la schermata quando glielo si chiede", async () => {
    const user = userEvent.setup();
    let shouldExplode = true;

    function Flaky(): React.JSX.Element {
      if (shouldExplode) throw new Error("boom");
      return <p>Contenuto</p>;
    }

    render(
      <ErrorBoundary>
        <Flaky />
      </ErrorBoundary>,
    );

    shouldExplode = false;
    await user.click(screen.getByRole("button", { name: "Riprova la schermata" }));

    expect(screen.getByText("Contenuto")).toBeInTheDocument();
  });

  it("dimentica l'errore quando si cambia schermata", () => {
    const { rerender } = render(
      <ErrorBoundary resetKey="/projects">
        <Explodes />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();

    // Navigare altrove non deve lasciare l'errore di prima sullo schermo.
    rerender(
      <ErrorBoundary resetKey="/clients">
        <p>Altra schermata</p>
      </ErrorBoundary>,
    );

    expect(screen.getByText("Altra schermata")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { setupUser } from "@/test/user";

import { i18n } from "@/lib/i18n";
import { HelpDialog } from "./HelpDialog";

function renderDialog() {
  const props = {
    onOpenChange: vi.fn(),
    onOpenProjects: vi.fn(),
    onOpenServiceStatus: vi.fn(),
  };
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
  );
  render(<HelpDialog open {...props} />, { wrapper });
  return props;
}

beforeAll(async () => {
  await i18n.changeLanguage("it");
});

describe("HelpDialog", () => {
  it("walks through an engagement in the order the product asks for it", () => {
    renderDialog();

    const steps = screen
      .getAllByRole("listitem")
      .map((item) => item.querySelector("p")?.textContent);

    expect(steps).toEqual([
      "Crea il progetto",
      "Aggiungi le fonti",
      "Ricostruisci il processo",
      "Chiudi le lacune",
      "Valida il modello",
    ]);
  });

  it("takes the consultant to the projects to start, closing itself", async () => {
    const user = setupUser();
    const props = renderDialog();

    await user.click(screen.getByRole("button", { name: /Vai ai progetti/ }));

    expect(props.onOpenChange).toHaveBeenCalledWith(false);
    expect(props.onOpenProjects).toHaveBeenCalled();
  });

  it("sends the consultant to the service status when something does not respond", async () => {
    const user = setupUser();
    const props = renderDialog();

    await user.click(screen.getByRole("button", { name: /stato del servizio/ }));

    expect(props.onOpenChange).toHaveBeenCalledWith(false);
    expect(props.onOpenServiceStatus).toHaveBeenCalled();
  });

  it("names the keys in the interface language", () => {
    renderDialog();

    expect(screen.getAllByText("Invio").length).toBeGreaterThan(0);
    expect(screen.getByText("Maiusc")).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { i18n } from "@/lib/i18n";

const loadProcessTranslations = vi.fn<() => Promise<void>>();

vi.mock("@/lib/i18n", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/i18n")>()),
  loadProcessTranslations: () => loadProcessTranslations(),
}));

// Il cruscotto vero legge il link e chiama il server: qui conta solo che parta.
vi.mock("./SharedDashboardApp", () => ({
  SharedDashboardApp: () => <p>cruscotto</p>,
}));

const { ShareRoot } = await import("./ShareRoot");

describe("ShareRoot", () => {
  beforeEach(async () => {
    loadProcessTranslations.mockReset();
    await i18n.changeLanguage("it");
  });

  it("mostra lo scheletro finche' le traduzioni non arrivano", () => {
    loadProcessTranslations.mockReturnValue(new Promise(() => {}));
    render(<ShareRoot />);

    expect(screen.getByLabelText("Caricamento…")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText("cruscotto")).not.toBeInTheDocument();
  });

  it("dice che non e' riuscita e Riprova richiede le traduzioni", async () => {
    loadProcessTranslations.mockRejectedValueOnce(new Error("rete giu'")).mockResolvedValueOnce(undefined);
    render(<ShareRoot />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Si è verificato un errore");
    expect(screen.queryByText("cruscotto")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Riprova" }));

    expect(await screen.findByText("cruscotto")).toBeInTheDocument();
    expect(loadProcessTranslations).toHaveBeenCalledTimes(2);
  });
});

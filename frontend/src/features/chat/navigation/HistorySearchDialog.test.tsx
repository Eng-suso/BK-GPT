import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { setupUser } from "@/test/user";
import { i18n } from "@/lib/i18n";

import type { ChatSessionHit } from "../types";

const searchChatSessions =
  vi.fn<(scopeKey: string, query: string) => Promise<ChatSessionHit[]>>();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    searchChatSessions: (scopeKey: string, query: string) =>
      searchChatSessions(scopeKey, query),
  };
});

const { HistorySearchDialog } = await import("./HistorySearchDialog");

function hit(overrides: Partial<ChatSessionHit> = {}): ChatSessionHit {
  return {
    threadId: "thread-1",
    title: "Ciclo passivo",
    updatedAt: "2026-01-01T10:00:00Z",
    messages: [],
    snippet: "Chi firma l'ordine al fornitore oltre i diecimila euro?",
    snippetRole: "user",
    matchCount: 2,
    ...overrides,
  };
}

function renderDialog(onSelectSession = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // L'istanza i18n vera, non un mock che restituisce le chiavi: cio' che si
  // verifica qui e' quello che il consulente legge davvero.
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </I18nextProvider>
  );
  render(
    <HistorySearchDialog
      open
      onOpenChange={vi.fn()}
      scopeKey="process:p-1"
      currentThreadId={null}
      locale="it"
      onSelectSession={onSelectSession}
    />,
    { wrapper },
  );
  return { onSelectSession };
}

beforeAll(async () => {
  await i18n.changeLanguage("it");
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("HistorySearchDialog", () => {
  it("shows the line that matched, not just the conversation title", async () => {
    const user = setupUser();
    searchChatSessions.mockResolvedValue([hit()]);
    renderDialog();

    await user.type(screen.getByRole("combobox"), "ordine fornitore");

    // Dieci conversazioni sullo stesso processo hanno titoli quasi identici:
    // cio' che dice quale riaprire e' la frase in cui la parola compare.
    expect(await screen.findByText(/diecimila euro/)).toBeInTheDocument();
    await waitFor(() =>
      expect(searchChatSessions).toHaveBeenCalledWith("process:p-1", "ordine fornitore"),
    );
  });

  it("does not ask the backend for one letter", async () => {
    const user = setupUser();
    searchChatSessions.mockResolvedValue([]);
    renderDialog();

    await user.type(screen.getByRole("combobox"), "o");

    await waitFor(() => expect(screen.getByText(/almeno 2 caratteri/i)).toBeInTheDocument());
    expect(searchChatSessions).not.toHaveBeenCalled();
  });

  it("opens the highlighted conversation with the keyboard", async () => {
    const user = setupUser();
    searchChatSessions.mockResolvedValue([
      hit(),
      hit({ threadId: "thread-2", title: "Accettazione merce", snippet: "ordine di acquisto" }),
    ]);
    const { onSelectSession } = renderDialog();

    await user.type(screen.getByRole("combobox"), "ordine");
    await screen.findByRole("option", { name: /Accettazione merce/ });

    await user.keyboard("{ArrowDown}{Enter}");

    expect(onSelectSession).toHaveBeenCalledWith("thread-2");
  });

  it("says nothing was found instead of showing an empty list", async () => {
    const user = setupUser();
    searchChatSessions.mockResolvedValue([]);
    renderDialog();

    await user.type(screen.getByRole("combobox"), "sconosciuto");

    expect(await screen.findByText(/Nessuna conversazione contiene/)).toBeInTheDocument();
  });

  it("offers a retry when the search fails, instead of an empty result", async () => {
    const user = setupUser();
    searchChatSessions.mockRejectedValue(new Error("backend giu'"));
    renderDialog();

    await user.type(screen.getByRole("combobox"), "ordine");

    // Un guasto che si mostra come "nessun risultato" fa concludere al
    // consulente che la conversazione non esiste.
    expect(await screen.findByText(/Ricerca non riuscita/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Riprova/ })).toBeInTheDocument();
  });
});

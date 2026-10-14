import { render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { i18n } from "@/lib/i18n";
import { setupUser } from "@/test/user";

// Il link nasce subito, come dal server: e' quello che rende attivo `hadLink`.
vi.mock("./ownerDashboardApi", () => ({
  useCreateOwnerLink: () => ({
    mutate: (_: unknown, options: { onSuccess: (created: { token: string }) => void }) => options.onSuccess({ token: "nuovo" }),
    reset: () => undefined,
    isPending: false,
    isError: false,
  }),
  ownerLinkUrl: (token: string) => `https://delir.test/share.html#${token}`,
}));

const { SendToClient } = await import("./SendToClient");

function renderSend(hadLink: boolean) {
  const props = { processId: "p1", owner: "Laura Conti", disabled: false, onSent: async () => undefined };
  const view = render(<I18nextProvider i18n={i18n}><SendToClient {...props} hadLink={hadLink} /></I18nextProvider>);
  return { ...view, setHadLink: (next: boolean) => view.rerender(<I18nextProvider i18n={i18n}><SendToClient {...props} hadLink={next} /></I18nextProvider>) };
}

describe("SendToClient", () => {
  beforeAll(async () => { await i18n.changeLanguage("it"); });

  it("does not warn about replacing a link that the dialog itself just created", async () => {
    const user = setupUser();
    const { setHadLink } = renderSend(false);

    await user.click(screen.getByRole("button", { name: /Invia al cliente/ }));
    setHadLink(true);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByText(/smette di funzionare/)).not.toBeInTheDocument();
  });

  it("warns when a link was already active before sending", async () => {
    const user = setupUser();
    renderSend(true);

    await user.click(screen.getByRole("button", { name: /Invia al cliente/ }));

    expect(screen.getByText(/smette di funzionare/)).toBeInTheDocument();
  });
});

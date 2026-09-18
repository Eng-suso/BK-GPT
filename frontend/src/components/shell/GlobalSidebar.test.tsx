import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { setupUser } from "@/test/user";

import { i18n } from "@/lib/i18n";
import { GlobalSidebar } from "./GlobalSidebar";

function renderSidebar(overrides: Partial<React.ComponentProps<typeof GlobalSidebar>> = {}) {
  const props = {
    activeSection: "projects" as const,
    onSectionChange: vi.fn(),
    onOpenHelp: vi.fn(),
    onOpenSettings: vi.fn(),
    ...overrides,
  };
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
  );
  render(<GlobalSidebar {...props} />, { wrapper });
  return props;
}

beforeAll(async () => {
  await i18n.changeLanguage("it");
});

describe("GlobalSidebar footer", () => {
  it("opens help and settings instead of doing nothing", async () => {
    const user = setupUser();
    const props = renderSidebar();

    await user.click(screen.getByRole("button", { name: "Aiuto" }));
    await user.click(screen.getByRole("button", { name: "Impostazioni" }));

    expect(props.onOpenHelp).toHaveBeenCalledTimes(1);
    expect(props.onOpenSettings).toHaveBeenCalledTimes(1);
  });

  it("marks settings as the current page and no section with it", () => {
    renderSidebar({ activeSection: null, settingsActive: true });

    expect(screen.getByRole("button", { name: "Impostazioni" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    // Sulle impostazioni nessuna sezione e' "quella aperta": prima la sidebar
    // evidenziava Progetti su qualunque pagina non riconosciuta.
    expect(screen.getByRole("button", { name: "Progetti" })).not.toHaveAttribute("aria-current");
  });
});

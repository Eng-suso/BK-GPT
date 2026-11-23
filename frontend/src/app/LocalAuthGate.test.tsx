import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";

import { i18n } from "@/lib/i18n";
import { authHeaders, clearSessionCredentials, websocketAuthMessage } from "@/lib/security";
import { HttpError } from "@/lib/http";
import { LocalAuthGate } from "./LocalAuthGate";

const fetchIdentity = vi.fn();
vi.mock("@/features/identity/api", () => ({ fetchIdentity: () => fetchIdentity() }));

afterEach(() => {
  vi.unstubAllEnvs();
  clearSessionCredentials();
  delete (window as Window & { DELIR_API_TOKEN?: string }).DELIR_API_TOKEN;
  delete (window as Window & { DELIR_TENANT_ID?: string }).DELIR_TENANT_ID;
  fetchIdentity.mockReset();
});

function mount() {
  return render(<I18nextProvider i18n={i18n}><LocalAuthGate><p>Workspace pronto</p></LocalAuthGate></I18nextProvider>);
}

describe("LocalAuthGate", () => {
  it("mostra l'app direttamente quando DEV non richiede credenziali", async () => {
    fetchIdentity.mockResolvedValue({ tenantId: "local" });
    mount();
    expect(await screen.findByText("Workspace pronto")).toBeInTheDocument();
  });

  it("chiede tenant e token per lo stack protetto e li usa solo dopo la verifica", async () => {
    vi.stubEnv("DEV", false);
    (window as Window & { DELIR_API_TOKEN?: string }).DELIR_API_TOKEN = "stale-token";
    (window as Window & { DELIR_TENANT_ID?: string }).DELIR_TENANT_ID = "stale-tenant";
    fetchIdentity.mockRejectedValueOnce(new HttpError(403, "forbidden"));
    fetchIdentity.mockResolvedValueOnce({ tenantId: "prod_sim" });
    mount();
    fireEvent.change(await screen.findByLabelText("Tenant"), { target: { value: "prod_sim" } });
    fireEvent.change(screen.getByLabelText("Token API"), { target: { value: "synthetic-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Entra" }));
    await waitFor(() => expect(screen.getByText("Workspace pronto")).toBeInTheDocument());
    expect(authHeaders().get("Authorization")).toBe("Bearer synthetic-token");
    expect(authHeaders().get("X-DeliR-Tenant-ID")).toBe("prod_sim");
    expect(JSON.parse(websocketAuthMessage())).toEqual({
      type: "auth", tenant_id: "prod_sim", api_token: "synthetic-token",
    });
    expect(window.sessionStorage.getItem("delir:session-api-token")).toBe("synthetic-token");
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";

import { i18n } from "@/lib/i18n";
import type { AuthConfig } from "@/lib/authConfig";
import { authHeaders, clearSessionCredentials, setAccessToken, websocketAuthMessage } from "@/lib/security";
import { HttpError } from "@/lib/http";
import { LocalAuthGate } from "./LocalAuthGate";

const fetchIdentity = vi.fn();
vi.mock("@/features/identity/api", () => ({ fetchIdentity: () => fetchIdentity() }));

const fetchAuthConfig = vi.fn<() => Promise<AuthConfig>>();
vi.mock("@/lib/authConfig", () => ({ fetchAuthConfig: () => fetchAuthConfig() }));

const restoreSupabaseSession = vi.fn<() => Promise<boolean>>();
const signInWithSupabase = vi.fn<(config: AuthConfig, email: string, password: string) => Promise<string>>();
const signOutOfSupabase = vi.fn<() => Promise<void>>();
vi.mock("@/lib/supabaseSession", () => ({
  restoreSupabaseSession: () => restoreSupabaseSession(),
  signInWithSupabase: (config: AuthConfig, email: string, password: string) => signInWithSupabase(config, email, password),
  signOutOfSupabase: () => signOutOfSupabase(),
}));

const TOKEN: AuthConfig = { provider: "token", supabaseUrl: "", supabasePublishableKey: "" };
const SUPABASE: AuthConfig = {
  provider: "supabase",
  supabaseUrl: "http://127.0.0.1:54321",
  supabasePublishableKey: "sb_publishable_test",
};

afterEach(() => {
  vi.unstubAllEnvs();
  clearSessionCredentials();
  delete (window as Window & { DELIR_API_TOKEN?: string }).DELIR_API_TOKEN;
  delete (window as Window & { DELIR_TENANT_ID?: string }).DELIR_TENANT_ID;
  for (const mock of [fetchIdentity, fetchAuthConfig, restoreSupabaseSession, signInWithSupabase, signOutOfSupabase]) {
    mock.mockReset();
  }
});

function mount() {
  return render(<I18nextProvider i18n={i18n}><LocalAuthGate><p>Workspace pronto</p></LocalAuthGate></I18nextProvider>);
}

async function signIn(email: string, password: string) {
  fireEvent.change(await screen.findByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Entra" }));
}

describe("LocalAuthGate", () => {
  it("mostra l'app direttamente quando DEV non richiede credenziali", async () => {
    fetchAuthConfig.mockResolvedValue({ ...TOKEN, provider: "local" });
    mount();
    expect(await screen.findByText("Workspace pronto")).toBeInTheDocument();
  });

  it("in DEV un backend che non risponde non blocca l'app", async () => {
    fetchAuthConfig.mockRejectedValue(new TypeError("Failed to fetch"));
    mount();
    expect(await screen.findByText("Workspace pronto")).toBeInTheDocument();
  });

  it("fuori da DEV un backend che non risponde e' detto, non aggirato", async () => {
    vi.stubEnv("DEV", false);
    fetchAuthConfig.mockRejectedValue(new TypeError("Failed to fetch"));
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("Il backend non risponde");
    expect(screen.queryByText("Workspace pronto")).not.toBeInTheDocument();
  });

  it("chiede tenant e token per lo stack protetto e li usa solo dopo la verifica", async () => {
    vi.stubEnv("DEV", false);
    fetchAuthConfig.mockResolvedValue(TOKEN);
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

  describe("con Supabase", () => {
    it("chiede email e password anche in DEV, senza campo token", async () => {
      fetchAuthConfig.mockResolvedValue(SUPABASE);
      restoreSupabaseSession.mockResolvedValue(false);
      mount();
      expect(await screen.findByLabelText("Email")).toBeInTheDocument();
      expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
      expect(screen.queryByLabelText("Token API")).not.toBeInTheDocument();
      // Lo spazio di lavoro e' l'account: non lo sceglie la persona.
      expect(screen.queryByLabelText("Tenant")).not.toBeInTheDocument();
      expect(screen.queryByText("Workspace pronto")).not.toBeInTheDocument();
    });

    it("entra con la sessione e manda al backend il suo access token", async () => {
      fetchAuthConfig.mockResolvedValue(SUPABASE);
      restoreSupabaseSession.mockResolvedValue(false);
      signInWithSupabase.mockImplementation(async () => {
        setAccessToken("jwt-della-sessione");
        return "ok";
      });
      fetchIdentity.mockResolvedValue({ tenantId: "pilot" });
      mount();
      await signIn("consulente@delir.test", "password-di-prova-123");

      await waitFor(() => expect(screen.getByText("Workspace pronto")).toBeInTheDocument());
      expect(signInWithSupabase).toHaveBeenCalledWith(SUPABASE, "consulente@delir.test", "password-di-prova-123");
      expect(authHeaders().get("Authorization")).toBe("Bearer jwt-della-sessione");
      // L'access token non finisce nello slot del token condiviso.
      expect(window.sessionStorage.getItem("delir:session-api-token")).toBeNull();
    });

    it("dice che le credenziali sono sbagliate senza dire quale", async () => {
      fetchAuthConfig.mockResolvedValue(SUPABASE);
      restoreSupabaseSession.mockResolvedValue(false);
      signInWithSupabase.mockResolvedValue("invalid");
      mount();
      await signIn("consulente@delir.test", "sbagliata-sbagliata");

      expect(await screen.findByRole("alert")).toHaveTextContent("Email o password non validi.");
      expect(fetchIdentity).not.toHaveBeenCalled();
    });

    it("se l'ambiente rifiuta l'account, esce dalla sessione appena aperta", async () => {
      fetchAuthConfig.mockResolvedValue(SUPABASE);
      restoreSupabaseSession.mockResolvedValue(false);
      signInWithSupabase.mockResolvedValue("ok");
      signOutOfSupabase.mockResolvedValue();
      fetchIdentity.mockRejectedValue(new HttpError(403, "forbidden"));
      mount();
      await signIn("consulente@delir.test", "password-di-prova-123");

      expect(await screen.findByRole("alert")).toHaveTextContent("non accetta il tuo account");
      expect(signOutOfSupabase).toHaveBeenCalledOnce();
      expect(screen.queryByText("Workspace pronto")).not.toBeInTheDocument();
    });

    it("una sessione gia' aperta nella scheda entra senza chiedere niente", async () => {
      fetchAuthConfig.mockResolvedValue(SUPABASE);
      restoreSupabaseSession.mockResolvedValue(true);
      fetchIdentity.mockResolvedValue({ tenantId: "pilot" });
      mount();
      expect(await screen.findByText("Workspace pronto")).toBeInTheDocument();
      expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    });
  });
});

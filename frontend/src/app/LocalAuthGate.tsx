import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { fetchIdentity } from "@/features/identity/api";
import { fetchAuthConfig, type AuthConfig } from "@/lib/authConfig";
import { HttpError } from "@/lib/http";
import { clearSessionCredentials, setSessionCredentials, setSessionTenant } from "@/lib/security";
import { restoreSupabaseSession, signInWithSupabase, signOutOfSupabase } from "@/lib/supabaseSession";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Surface } from "@/ui/surface";

type GateState = "checking" | "locked" | "ready" | "unavailable";

const LOCAL_CONFIG: AuthConfig = { provider: "local", supabaseUrl: "", supabasePublishableKey: "" };

function isRejected(cause: unknown): boolean {
  return cause instanceof HttpError && (cause.status === 401 || cause.status === 403);
}

type GateResult = { config: AuthConfig; state: Exclude<GateState, "checking"> };

/**
 * Decides, without touching React state, whether this tab may enter: reads how
 * the backend authenticates, restores an open Supabase session, proves it.
 */
async function evaluateGate(): Promise<GateResult> {
  let config: AuthConfig;
  try {
    config = await fetchAuthConfig();
  } catch {
    // In development a backend that cannot be asked (stopped, or replaced by
    // `page.route` in the frontend-only e2e) keeps the old behaviour.
    return { config: LOCAL_CONFIG, state: import.meta.env.DEV ? "ready" : "unavailable" };
  }
  if (config.provider === "local" || (import.meta.env.DEV && config.provider === "token")) {
    return { config, state: "ready" };
  }
  try {
    if (config.provider === "supabase" && !(await restoreSupabaseSession(config))) {
      return { config, state: "locked" };
    }
    await fetchIdentity();
    return { config, state: "ready" };
  } catch (cause) {
    if (isRejected(cause)) {
      clearSessionCredentials();
      return { config, state: "locked" };
    }
    return { config, state: "unavailable" };
  }
}

/**
 * Keeps protected queries from running before this browser session is authenticated.
 *
 * The backend says how (`/v1/auth/config`): no gate, the shared token of the
 * pilot, or a personal Supabase login. See `evaluateGate`.
 */
export function LocalAuthGate({ children }: { children: ReactNode }): React.JSX.Element {
  const { t } = useTranslation("common");
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [state, setState] = useState<GateState>("checking");
  const [tenant, setTenant] = useState("");
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function apply(result: GateResult): void {
    setConfig(result.config);
    setState(result.state);
  }

  useEffect(() => {
    let active = true;
    void evaluateGate().then((result) => {
      if (active) apply(result);
    });
    return () => { active = false; };
  }, []);

  function retry(): void {
    setState("checking");
    void evaluateGate().then(apply);
  }

  async function submitToken(): Promise<void> {
    setSessionCredentials(token.trim(), tenant.trim());
    try {
      await fetchIdentity();
      setToken("");
      setState("ready");
    } catch (cause) {
      clearSessionCredentials();
      setError(isRejected(cause) ? t("localAuth.invalid") : t("localAuth.unavailable"));
    }
  }

  async function submitSupabase(current: AuthConfig): Promise<void> {
    const result = await signInWithSupabase(current, email.trim(), password);
    if (result !== "ok") {
      setError(result === "invalid" ? t("localAuth.invalidLogin") : t("localAuth.unavailable"));
      return;
    }
    setSessionTenant(tenant.trim());
    try {
      await fetchIdentity();
      setPassword("");
      setState("ready");
    } catch (cause) {
      // Login riuscito ma il backend rifiuta (tenant fuori allowlist, sessione
      // non valida per questo progetto): si esce, per non restare a meta'.
      await signOutOfSupabase();
      setError(isRejected(cause) ? t("localAuth.invalidTenant") : t("localAuth.unavailable"));
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting || !config) return;
    setError("");
    setSubmitting(true);
    try {
      if (config.provider === "supabase") await submitSupabase(config);
      else await submitToken();
    } finally {
      setSubmitting(false);
    }
  }

  if (state === "ready") return <>{children}</>;
  const personal = config?.provider === "supabase";
  return (
    <main className="app-material flex min-h-dvh items-center justify-center bg-background p-4">
      <Surface variant="panel" className="w-full max-w-md space-y-5 p-6 sm:p-8">
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-foreground">{t("localAuth.title")}</h1>
          <p className="text-sm text-muted-foreground">
            {t(personal ? "localAuth.personalDescription" : "localAuth.description")}
          </p>
        </div>
        {state === "checking" && <p role="status" className="text-sm text-muted-foreground">{t("state.loading")}</p>}
        {state === "unavailable" && (
          <div className="space-y-3">
            <p role="alert" className="text-sm text-destructive">{t("localAuth.unavailable")}</p>
            <Button type="button" variant="outline" onClick={retry}>{t("actions.retry")}</Button>
          </div>
        )}
        {state === "locked" && (
          <form className="space-y-4" onSubmit={(event) => void submit(event)} aria-busy={submitting}>
            <div className="space-y-1.5">
              <label htmlFor="local-auth-tenant" className="text-sm font-medium">{t("localAuth.tenant")}</label>
              <Input id="local-auth-tenant" autoComplete="off" required value={tenant} onChange={(event) => setTenant(event.target.value)} />
            </div>
            {personal ? (
              <>
                <div className="space-y-1.5">
                  <label htmlFor="local-auth-email" className="text-sm font-medium">{t("localAuth.email")}</label>
                  <Input id="local-auth-email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="local-auth-password" className="text-sm font-medium">{t("localAuth.password")}</label>
                  <Input id="local-auth-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
                </div>
              </>
            ) : (
              <div className="space-y-1.5">
                <label htmlFor="local-auth-token" className="text-sm font-medium">{t("localAuth.token")}</label>
                <Input id="local-auth-token" type="password" autoComplete="off" required value={token} onChange={(event) => setToken(event.target.value)} />
              </div>
            )}
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? t("localAuth.entering") : t("localAuth.enter")}
            </Button>
          </form>
        )}
      </Surface>
    </main>
  );
}

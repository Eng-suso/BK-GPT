import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { fetchIdentity } from "@/features/identity/api";
import { HttpError } from "@/lib/http";
import { clearSessionCredentials, setSessionCredentials } from "@/lib/security";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Surface } from "@/ui/surface";

type GateState = "checking" | "locked" | "ready" | "unavailable";

/** Keeps protected queries from running before this browser session is authenticated. */
export function LocalAuthGate({ children }: { children: ReactNode }): React.JSX.Element {
  if (import.meta.env.DEV) return <>{children}</>;
  return <ProtectedLocalAuthGate>{children}</ProtectedLocalAuthGate>;
}

function ProtectedLocalAuthGate({ children }: { children: ReactNode }): React.JSX.Element {
  const { t } = useTranslation("common");
  const [state, setState] = useState<GateState>("checking");
  const [tenant, setTenant] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");

  async function check(): Promise<void> {
    try {
      await fetchIdentity();
      setState("ready");
    } catch (cause) {
      if (cause instanceof HttpError && (cause.status === 401 || cause.status === 403)) {
        clearSessionCredentials();
        setState("locked");
      } else {
        setState("unavailable");
      }
    }
  }

  useEffect(() => {
    let active = true;
    void fetchIdentity().then(() => {
      if (active) setState("ready");
    }).catch((cause: unknown) => {
      if (!active) return;
      if (cause instanceof HttpError && (cause.status === 401 || cause.status === 403)) {
        clearSessionCredentials();
        setState("locked");
      } else {
        setState("unavailable");
      }
    });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError("");
    setSessionCredentials(token.trim(), tenant.trim());
    try {
      await fetchIdentity();
      setToken("");
      setState("ready");
    } catch (cause) {
      clearSessionCredentials();
      setError(cause instanceof HttpError && (cause.status === 401 || cause.status === 403)
        ? t("localAuth.invalid") : t("localAuth.unavailable"));
      setState("locked");
    }
  }

  if (state === "ready") return <>{children}</>;
  return (
    <main className="app-material flex min-h-dvh items-center justify-center bg-background p-4">
      <Surface variant="panel" className="w-full max-w-md space-y-5 p-6 sm:p-8">
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-foreground">{t("localAuth.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("localAuth.description")}</p>
        </div>
        {state === "checking" && <p role="status" className="text-sm text-muted-foreground">{t("state.loading")}</p>}
        {state === "unavailable" && (
          <div className="space-y-3">
            <p role="alert" className="text-sm text-destructive">{t("localAuth.unavailable")}</p>
            <Button type="button" variant="outline" onClick={() => { setState("checking"); void check(); }}>{t("actions.retry")}</Button>
          </div>
        )}
        {state === "locked" && (
          <form className="space-y-4" onSubmit={(event) => void submit(event)}>
            <div className="space-y-1.5">
              <label htmlFor="local-auth-tenant" className="text-sm font-medium">{t("localAuth.tenant")}</label>
              <Input id="local-auth-tenant" autoComplete="off" required value={tenant} onChange={(event) => setTenant(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="local-auth-token" className="text-sm font-medium">{t("localAuth.token")}</label>
              <Input id="local-auth-token" type="password" autoComplete="off" required value={token} onChange={(event) => setToken(event.target.value)} />
            </div>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full">{t("localAuth.enter")}</Button>
          </form>
        )}
      </Surface>
    </main>
  );
}

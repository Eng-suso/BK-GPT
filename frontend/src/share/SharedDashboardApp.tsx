import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, Link2Off, RefreshCw } from "lucide-react";

import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { Surface } from "@/ui/surface";
import type { OwnerDashboardData } from "@/features/process/handover/dashboardContract";
import { OwnerDashboardView } from "@/features/process/handover/OwnerDashboardView";
import { InvalidShareLink, fetchSharedDashboard, tokenFromHash } from "./fetchSharedDashboard";

// Una richiesta per codice e tentativo: se React ripete l'effetto (in sviluppo
// lo fa apposta) riusa quella partita, e il server conta una visita sola.
const requests = new Map<string, Promise<OwnerDashboardData>>();
function load(token: string, attempt: number): Promise<OwnerDashboardData> {
  const key = `${attempt}:${token}`;
  if (!requests.has(key)) requests.set(key, fetchSharedDashboard(token));
  return requests.get(key)!;
}

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: OwnerDashboardData }
  | { kind: "invalid" }
  | { kind: "error" };

/** La pagina che il responsabile del processo apre dal link del consulente. */
export function SharedDashboardApp(): React.JSX.Element {
  const { t } = useTranslation("process");
  const [token] = useState(() => tokenFromHash(window.location.hash));
  const [state, setState] = useState<State>(() => (token ? { kind: "loading" } : { kind: "invalid" }));
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => { setState({ kind: "loading" }); setAttempt((value) => value + 1); }, []);

  useEffect(() => {
    if (!token) return;
    let current = true;
    load(token, attempt)
      .then((data) => { if (!current) return; document.title = `${data.processName} · ${t("handover.dashboard.title")}`; setState({ kind: "ready", data }); })
      .catch((error: unknown) => { if (current) setState({ kind: error instanceof InvalidShareLink ? "invalid" : "error" }); });
    return () => { current = false; };
  }, [attempt, t, token]);

  if (state.kind === "ready") {
    return (
      <OwnerDashboardView
        data={state.data}
        toolbar={(
          <div className="owner-dashboard-toolbar" role="region" aria-label={t("handover.dashboard.share.personal")}>
            <p className="owner-dashboard-preview">{t("handover.dashboard.share.personal")}</p>
            <Button size="sm" onClick={() => window.print()}><Download aria-hidden />{t("handover.dashboard.download")}</Button>
          </div>
        )}
      />
    );
  }
  if (state.kind === "loading") {
    return (
      <div className="owner-dashboard" aria-busy="true" aria-label={t("handover.dashboard.share.loading")}>
        <div className="owner-dashboard-page"><Skeleton className="h-10 w-80" /><Skeleton className="h-28 w-full" /><Skeleton className="h-64 w-full" /></div>
      </div>
    );
  }
  const invalid = state.kind === "invalid";
  return (
    <div className="owner-dashboard">
      <main className="owner-dashboard-page">
        <Surface variant="panel" className="owner-dashboard-status" role={invalid ? "status" : "alert"}>
          <h1 className="inline-flex items-center gap-2 text-base font-semibold">{invalid ? <Link2Off aria-hidden className="size-4" /> : <RefreshCw aria-hidden className="size-4" />}{t(invalid ? "handover.dashboard.share.invalidTitle" : "handover.dashboard.share.errorTitle")}</h1>
          <p>{t(invalid ? "handover.dashboard.share.invalidBody" : "handover.dashboard.share.errorBody")}</p>
          {!invalid && <div><Button size="sm" variant="outline" onClick={retry}>{t("handover.dashboard.share.retry")}</Button></div>}
        </Surface>
      </main>
    </div>
  );
}

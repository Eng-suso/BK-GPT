import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { loadProcessTranslations } from "@/lib/i18n";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { Surface } from "@/ui/surface";
import { SharedDashboardApp } from "./SharedDashboardApp";

/**
 * Lo scheletro del cruscotto, finche' mancano le parole o i dati.
 *
 * Senza testo: l'etichetta del cruscotto sta in `process.json`, che e' proprio
 * quello che si sta aspettando.
 */
export function ShareSkeleton(): React.JSX.Element {
  const { t } = useTranslation("common");
  return (
    <div className="owner-dashboard" aria-busy="true" aria-label={t("state.loading")}>
      <div className="owner-dashboard-page"><Skeleton className="h-10 w-80" /><Skeleton className="h-28 w-full" /><Skeleton className="h-64 w-full" /></div>
    </div>
  );
}

/**
 * La pagina del cliente parte solo con le sue traduzioni.
 *
 * `process.json` arriva a richiesta (`src/lib/i18n`). Se non arriva, la pagina
 * lo dice con le parole di `common`, che sono nel pacchetto, e "Riprova" lo
 * richiede: il tasto del cruscotto ripeterebbe solo la lettura dei dati.
 */
export function ShareRoot(): React.JSX.Element {
  const { t } = useTranslation("common");
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => { setState("loading"); setAttempt((value) => value + 1); }, []);

  useEffect(() => {
    let current = true;
    loadProcessTranslations().then(
      () => { if (current) setState("ready"); },
      () => { if (current) setState("failed"); },
    );
    return () => { current = false; };
  }, [attempt]);

  if (state === "ready") return <SharedDashboardApp />;
  if (state === "loading") return <ShareSkeleton />;
  return (
    <div className="owner-dashboard">
      <main className="owner-dashboard-page">
        <Surface variant="panel" className="owner-dashboard-status" role="alert">
          <h1 className="inline-flex items-center gap-2 text-base font-semibold"><RefreshCw aria-hidden className="size-4" />{t("state.error")}</h1>
          <p>{t("state.errorBody")}</p>
          <div><Button size="sm" variant="outline" onClick={retry}>{t("actions.retry")}</Button></div>
        </Surface>
      </main>
    </div>
  );
}

import React from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Server, ShieldCheck, XCircle } from "lucide-react";

import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { cn } from "@/lib/utils";
import { fetchEgressInventory, statusKeys, type EgressRoute } from "./api";

type Tone = "external" | "internal" | "blocked";

function toneOf(route: EgressRoute): Tone {
  if (!route.allowed) return "blocked";
  return route.internal ? "internal" : "external";
}

function EgressRow({ route }: { route: EgressRoute }): React.JSX.Element {
  const { t } = useTranslation("common");
  const tone = toneOf(route);
  const Icon = tone === "blocked" ? XCircle : tone === "internal" ? Server : ShieldCheck;

  return (
    <li className="flex items-start gap-2.5 border-b border-border py-2.5 last:border-b-0">
      <Icon
        className={cn(
          "mt-0.5 size-4 shrink-0",
          tone === "blocked" && "text-[var(--color-status-danger)]",
          tone === "internal" && "text-muted-foreground",
          tone === "external" && "text-[var(--color-status-warning)]",
        )}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
          <p className="text-body-sm font-medium text-foreground">{route.purpose}</p>
          <span className="break-all font-mono text-xs text-muted-foreground">{route.host}</span>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {tone === "blocked"
            ? t("dataEgress.blocked")
            : tone === "internal"
              ? t("dataEgress.internal")
              : t("dataEgress.external")}
        </p>
        <ul className="mt-1.5 flex flex-wrap gap-1" aria-label={t("dataEgress.dataLabel")}>
          {route.data.map((category) => (
            <li key={category}>
              <Badge variant="outline">{t(`dataEgress.category.${category}`)}</Badge>
            </li>
          ))}
        </ul>
      </div>
    </li>
  );
}

/**
 * Dove escono i dati del cliente, con la configurazione di questo ambiente.
 *
 * La domanda di ogni questionario di sicurezza - quali fornitori ricevono cosa -
 * letta dal backend e non da un documento che puo' invecchiare. Le destinazioni
 * spente non compaiono: qui si vede cosa esce adesso. L'elenco completo, con lo
 * stato contrattuale di ogni fornitore, sta in docs/compliance.
 */
export function DataEgressPanel(): React.JSX.Element {
  const { t } = useTranslation("common");
  const inventory = useQuery({
    queryKey: statusKeys.egress(),
    queryFn: fetchEgressInventory,
    staleTime: 30_000,
    retry: false,
  });

  if (inventory.isError) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2" role="alert">
        <p className="text-body-sm text-muted-foreground">{t("dataEgress.failed")}</p>
        <Button variant="outline" size="sm" onClick={() => void inventory.refetch()}>
          {t("serviceStatus.refresh")}
        </Button>
      </div>
    );
  }

  if (!inventory.data) {
    return (
      <p className="flex items-center gap-2 text-body-sm text-muted-foreground" role="status">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        {t("serviceStatus.checking")}
      </p>
    );
  }

  const active = inventory.data.routes.filter((route) => route.active);
  const external = active.filter((route) => !route.internal);

  return (
    <div>
      <p className="text-xs leading-5 text-muted-foreground">
        {external.length === 0
          ? t("dataEgress.noneExternal")
          : t("dataEgress.summary", { count: external.length })}{" "}
        {inventory.data.enforced ? t("dataEgress.enforced") : t("dataEgress.notEnforced")}
      </p>
      <ul className="mt-2 flex flex-col">
        {active.map((route) => (
          <EgressRow key={route.destination} route={route} />
        ))}
      </ul>
      {inventory.data.localTracePayload ? (
        <p className="mt-3 flex items-start gap-2 text-xs leading-5 text-muted-foreground">
          <AlertTriangle
            className="mt-0.5 size-3.5 shrink-0 text-[var(--color-status-warning)]"
            aria-hidden="true"
          />
          {t("dataEgress.localTracePayload")}
        </p>
      ) : null}
    </div>
  );
}

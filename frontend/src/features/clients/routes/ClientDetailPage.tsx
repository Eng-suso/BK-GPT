import { useId } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";

import { PageHeader } from "@/components/layout";
import { ErrorState } from "@/components/feedback";
import { StatusIndicator } from "@/components/status";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { ROUTES } from "@/app/routes";
import { useClientSourcesQuery } from "@/features/projects/api";
import { SourcesPanel } from "@/features/projects/components/SourcesPanel";
import { useClientsQuery } from "../api";
import { clientStatusTone } from "../types";

/**
 * La pagina del cliente: chi e', e i file che valgono per tutti i suoi
 * progetti (P1.16).
 *
 * Un file caricato per tutto il cliente compare nelle Fonti di ogni progetto,
 * ma non appartiene a nessuno di loro: qui sta a casa sua, e la ricerca globale
 * porta qui. I progetti restano nella loro lista, gia' filtrata per cliente.
 */
export function ClientDetailPage(): React.JSX.Element {
  const { clientId = "" } = useParams();
  const { t } = useTranslation("clients");
  const navigate = useNavigate();
  const sourcesHeadingId = useId();
  const clientsQ = useClientsQuery();
  const sourcesQ = useClientSourcesQuery(clientId);
  const client = clientsQ.data?.find((item) => item.id === clientId) ?? null;

  if (clientsQ.isLoading) {
    return (
      <div className="flex flex-col gap-4 px-7 py-6">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-7 w-80" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (clientsQ.isError || !client) {
    // Un cliente che non c'e' (eliminato, archiviato, indirizzo vecchio) non
    // ricompare riprovando: lo si dice, e si torna all'elenco.
    return (
      <div className="flex flex-1 items-center justify-center">
        <ErrorState
          title={clientsQ.isError ? undefined : t("page.missing.title")}
          description={clientsQ.isError ? t("state.loadError") : t("page.missing.body")}
          onRetry={clientsQ.isError ? () => void clientsQ.refetch() : undefined}
          action={
            <Button variant="ghost" size="sm" onClick={() => navigate(ROUTES.clients.list)}>
              {t("page.backToList")}
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-6 overflow-auto bg-card px-7 py-6">
      <PageHeader
        breadcrumbs={[
          { label: t("breadcrumb.clients"), to: ROUTES.clients.list },
          { label: client.name },
        ]}
        title={client.name}
        meta={
          <>
            {client.sector ? (
              <>
                <span>{client.sector}</span>
                <span aria-hidden>·</span>
              </>
            ) : null}
            <StatusIndicator tone={clientStatusTone(client.status)} label={client.status} />
            {client.owner ? (
              <>
                <span aria-hidden>·</span>
                <span>{client.owner}</span>
              </>
            ) : null}
          </>
        }
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              navigate(`${ROUTES.projects.list}?f_client=${encodeURIComponent(client.id)}`)
            }
          >
            <ArrowRight aria-hidden /> {t("page.openProjects")}
          </Button>
        }
      />

      <section aria-labelledby={sourcesHeadingId} className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h2 id={sourcesHeadingId} className="text-sm font-semibold text-foreground">
            {t("page.sources.title")}
          </h2>
          <p className="text-xs text-muted-foreground">{t("page.sources.description")}</p>
        </div>
        {sourcesQ.isError ? (
          <ErrorState description={t("page.sources.loadError")} onRetry={() => void sourcesQ.refetch()} />
        ) : sourcesQ.isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <SourcesPanel
            projectId={null}
            client={{ id: client.id, name: client.name }}
            sources={sourcesQ.data ?? []}
            processes={[]}
          />
        )}
      </section>
    </div>
  );
}

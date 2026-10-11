import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Download } from "lucide-react";

import { ROUTES } from "@/app/routes";
import { ErrorState } from "@/components/feedback";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { useOwnerDashboardPreview } from "./ownerDashboardApi";
import { OwnerDashboardView } from "./OwnerDashboardView";

/**
 * L'anteprima del consulente: il cruscotto che il server manda al link del
 * cliente, con in piu' la barra per tornare alla consegna e scaricare il PDF.
 */
export function OwnerDashboardPage(): React.JSX.Element {
  const { projectId = "", processId = "" } = useParams();
  const { t } = useTranslation("process");
  const navigate = useNavigate();
  const preview = useOwnerDashboardPreview(processId);
  const back = () => navigate(ROUTES.projects.handover(projectId, processId));

  if (preview.isLoading) {
    return (
      <div className="owner-dashboard" aria-busy="true" aria-label={t("handover.loading")}>
        <div className="owner-dashboard-page"><Skeleton className="h-10 w-80" /><Skeleton className="h-28 w-full" /><Skeleton className="h-64 w-full" /></div>
      </div>
    );
  }
  if (preview.isError || !preview.data) {
    return (
      <div className="flex h-dvh items-center justify-center">
        <ErrorState
          description={t("state.loadError")}
          onRetry={() => void preview.refetch()}
          action={<Button variant="ghost" size="sm" onClick={back}>{t("handover.dashboard.back")}</Button>}
        />
      </div>
    );
  }
  return (
    <OwnerDashboardView
      data={preview.data}
      toolbar={(
        <div className="owner-dashboard-toolbar" role="region" aria-label={t("handover.dashboard.preview")}>
          <Button variant="ghost" size="sm" onClick={back}><ArrowLeft aria-hidden />{t("handover.dashboard.back")}</Button>
          <p className="owner-dashboard-preview">{t("handover.dashboard.preview")}</p>
          <Button size="sm" onClick={() => window.print()}><Download aria-hidden />{t("handover.dashboard.download")}</Button>
        </div>
      )}
    />
  );
}

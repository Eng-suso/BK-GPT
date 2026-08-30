import { useTranslation } from "react-i18next";
import { Boxes } from "lucide-react";

import { PageHeader } from "@/components/layout";
import { EmptyState } from "@/components/feedback";

/**
 * Model library. No backend endpoint yet — the page is scaffolded so it
 * lights up once `/v1/workspace/models` exists.
 */
export function ModelsPage(): React.JSX.Element {
  const { t } = useTranslation("common");

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto px-7 py-6">
      <PageHeader
        breadcrumbs={[{ label: t("nav.models") }]}
        title={t("nav.models")}
        description={t("models.description")}
      />
      <div className="flex flex-1 items-center justify-center rounded-xl border border-border bg-card">
        <EmptyState
          icon={Boxes}
          title={t("state.comingSoon")}
          description={t("models.empty")}
        />
      </div>
    </div>
  );
}

import { useTranslation } from "react-i18next";
import { Archive } from "lucide-react";

import { PageHeader } from "@/components/layout";
import { EmptyState } from "@/components/feedback";

/**
 * Document archive. No backend endpoint yet — scaffolded for when
 * `/v1/workspace/documents` exists.
 */
export function ArchivePage(): React.JSX.Element {
  const { t } = useTranslation("common");

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto px-7 py-6">
      <PageHeader
        breadcrumbs={[{ label: t("nav.archive") }]}
        title={t("nav.archive")}
        description={t("archive.description")}
      />
      <div className="flex flex-1 items-center justify-center rounded-xl border border-border bg-card">
        <EmptyState
          icon={Archive}
          title={t("state.comingSoon")}
          description={t("archive.empty")}
        />
      </div>
    </div>
  );
}

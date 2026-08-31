import React from "react";
import { useTranslation } from "react-i18next";
import type { LucideIcon } from "lucide-react";

import { EmptyState } from "@/components/feedback";

type PhasePlaceholderProps = {
  /** i18n key under `simulation.section.nav.*` for the screen name. */
  screenKey: string;
  icon: LucideIcon;
};

/**
 * Temporary body for a Simulation sub-screen that ships in a later phase.
 * Keeps the route + navigation live so the section shell can be reviewed now.
 */
export function PhasePlaceholder({
  screenKey,
  icon,
}: PhasePlaceholderProps): React.JSX.Element {
  const { t } = useTranslation("process");
  return (
    <div className="flex h-full items-center justify-center p-6">
      <EmptyState
        icon={icon}
        title={t(`simulation.section.nav.${screenKey}`)}
        description={t("simulation.section.comingSoon")}
      />
    </div>
  );
}

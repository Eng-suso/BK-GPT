import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Compass } from "lucide-react";

import { EmptyState } from "@/components/feedback";
import { Button } from "@/ui/button";
import { ROUTES } from "@/app/routes";

/**
 * Un indirizzo che non porta da nessuna parte lo dice.
 *
 * Prima `path: "*"` rimandava a `/projects` con un `Navigate replace`: un link
 * vecchio, un processo cancellato o un refuso atterravano su un elenco senza
 * una parola di spiegazione, e il tasto indietro non tornava perché la rotta
 * sbagliata era già stata sostituita nella cronologia.
 */
export function NotFoundPage(): React.JSX.Element {
  const { t } = useTranslation("common");
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="flex h-full items-center justify-center p-6">
      <EmptyState
        icon={Compass}
        title={t("notFound.title")}
        description={t("notFound.body", { path: location.pathname })}
        action={
          <Button size="sm" onClick={() => navigate(ROUTES.projects.list)}>
            {t("notFound.action")}
          </Button>
        }
      />
    </div>
  );
}

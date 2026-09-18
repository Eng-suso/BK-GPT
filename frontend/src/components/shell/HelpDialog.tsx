import { useTranslation } from "react-i18next";
import { Activity, ArrowRight } from "lucide-react";

import { Button } from "@/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";

export interface HelpDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Porta all'elenco progetti, da cui parte ogni incarico. */
  onOpenProjects: () => void;
  /** Apre lo stato del servizio: la prima domanda quando qualcosa non risponde. */
  onOpenServiceStatus: () => void;
}

/** I passi di un incarico, nell'ordine in cui il prodotto li chiede. */
const WORKFLOW_STEPS = ["project", "sources", "reconstruct", "gaps", "validate"] as const;

/**
 * Le scorciatoie che esistono davvero nel codice, non un elenco aspirazionale.
 * Chi aggiunge o toglie una scorciatoia aggiorna questa lista.
 */
const SHORTCUTS = [
  { keys: ["enter"], id: "send" },
  { keys: ["shift", "enter"], id: "newline" },
  { keys: ["1", "…", "9"], id: "answer" },
  { keys: ["↑", "↓", "enter"], id: "search" },
  { keys: ["esc"], id: "close" },
  { keys: ["←", "→", "home", "end"], id: "resize" },
] as const;

/** I tasti con un nome cambiano con la lingua della tastiera; frecce e cifre no. */
const NAMED_KEYS = new Set(["enter", "shift", "esc", "home", "end"]);

/**
 * Aiuto: come si porta avanti un incarico, e cosa fare quando qualcosa non va.
 *
 * Il bottone "Aiuto" della sidebar non aveva azione. Qui c'e' il percorso di
 * lavoro che il prodotto si aspetta, le scorciatoie reali, e il primo controllo
 * da fare quando qualcosa non risponde.
 */
export function HelpDialog({
  open,
  onOpenChange,
  onOpenProjects,
  onOpenServiceStatus,
}: HelpDialogProps): React.JSX.Element {
  const { t } = useTranslation("common");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85dvh] flex-col gap-5 overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("help.title")}</DialogTitle>
          <DialogDescription>{t("help.description")}</DialogDescription>
        </DialogHeader>

        <section aria-labelledby="help-workflow">
          <h3
            id="help-workflow"
            className="mb-2 text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground"
          >
            {t("help.workflow.title")}
          </h3>
          <ol className="flex flex-col gap-2">
            {WORKFLOW_STEPS.map((step, index) => (
              <li key={step} className="flex gap-3">
                <span className="grid size-6 shrink-0 place-items-center rounded-full border border-border text-[11px] font-semibold tabular-nums text-muted-foreground">
                  {index + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-foreground">
                    {t(`help.workflow.${step}.title`)}
                  </p>
                  <p className="text-[12.5px] leading-5 text-muted-foreground">
                    {t(`help.workflow.${step}.body`)}
                  </p>
                </div>
              </li>
            ))}
          </ol>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => {
              onOpenChange(false);
              onOpenProjects();
            }}
          >
            {t("help.workflow.start")}
            <ArrowRight />
          </Button>
        </section>

        <section aria-labelledby="help-shortcuts">
          <h3
            id="help-shortcuts"
            className="mb-2 text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground"
          >
            {t("help.shortcuts.title")}
          </h3>
          <dl className="flex flex-col">
            {SHORTCUTS.map((shortcut) => (
              <div
                key={shortcut.id}
                className="flex items-center justify-between gap-3 border-b border-border py-2 last:border-b-0"
              >
                <dt className="text-[12.5px] text-muted-foreground">
                  {t(`help.shortcuts.${shortcut.id}`)}
                </dt>
                <dd className="flex shrink-0 gap-1">
                  {shortcut.keys.map((key) => (
                    <kbd
                      key={key}
                      className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground"
                    >
                      {NAMED_KEYS.has(key) ? t(`help.keys.${key}`) : key}
                    </kbd>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
        </section>

        <section aria-labelledby="help-trouble">
          <h3
            id="help-trouble"
            className="mb-2 text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground"
          >
            {t("help.trouble.title")}
          </h3>
          <p className="text-[12.5px] leading-5 text-muted-foreground">{t("help.trouble.body")}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => {
              onOpenChange(false);
              onOpenServiceStatus();
            }}
          >
            <Activity />
            {t("help.trouble.action")}
          </Button>
        </section>
      </DialogContent>
    </Dialog>
  );
}

import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/ui/dialog";
import { Button } from "@/ui/button";

export type ConfirmDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Cosa succede confermando, e cosa non si potrà più tornare a prendere. */
  description: string;
  confirmLabel: string;
  /** `true` colora l'azione come distruttiva. */
  destructive?: boolean;
  onConfirm: () => void | Promise<void>;
};

/**
 * La domanda prima di un'azione che non si annulla.
 *
 * Esisteva già per i record del workspace (`RecordLifecycleDialog`, che per
 * eliminare chiede persino di riscrivere il nome) e non esisteva per la chat,
 * dove «Elimina cronologia» partiva al click e portava via tutte le
 * conversazioni dello spazio. Due pesi diversi per la stessa perdita.
 *
 * Qui non si chiede di riscrivere niente: una conversazione non trascina con sé
 * altri record, e una conferma sproporzionata si impara a cliccare senza
 * leggerla.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive = false,
  onConfirm,
}: ConfirmDialogProps): React.JSX.Element {
  const { t } = useTranslation("common");
  const [isWorking, setIsWorking] = useState(false);

  const confirm = async () => {
    if (isWorking) return;
    setIsWorking(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setIsWorking(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={isWorking}
          >
            {t("actions.cancel")}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            size="sm"
            onClick={() => void confirm()}
            disabled={isWorking}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

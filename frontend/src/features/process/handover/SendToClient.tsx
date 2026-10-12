import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Copy, Loader2, Send } from "lucide-react";

import { InlineNotice } from "@/components/feedback/InlineNotice";
import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/ui/dialog";
import { Input } from "@/ui/input";
import { ownerLinkUrl, useCreateOwnerLink } from "./ownerDashboardApi";

/**
 * Inviare al cliente e' un gesto solo: DeliR prepara il link, il consulente lo
 * copia e lo manda, poi conferma. Lo stato passa "in attesa della risposta"
 * solo dopo la conferma, cosi' non dice mai di aver inviato qualcosa che il
 * consulente non ha ancora mandato.
 */
export function SendToClient({ processId, owner, hadLink, disabled, onSent }: {
  processId: string;
  owner: string;
  /** C'era gia' un link attivo: crearne uno nuovo lo sostituisce. */
  hadLink: boolean;
  disabled: boolean;
  onSent: () => Promise<void>;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const k = (key: string, options?: Record<string, unknown>) => t(`handover.send.${key}`, options);
  const urlId = useId();
  const create = useCreateOwnerLink(processId);
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState(false);

  const prepare = () => {
    create.mutate(undefined, { onSuccess: (created) => setUrl(ownerLinkUrl(created.token)) });
  };
  // Il link nasce dal click, non da un effetto: un effetto ripetuto ne
  // creerebbe due, e il primo, gia' revocato, potrebbe finire sullo schermo.
  const start = () => { setOpen(true); prepare(); };
  const change = (next: boolean) => {
    if (sending || next) return;
    setOpen(false); setUrl(null); setSendError(false); create.reset();
  };
  const copy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      toast.success(t("handover.link.copied"));
    } catch {
      document.getElementById(urlId)?.focus();
    }
  };
  const confirm = async () => {
    setSending(true);
    setSendError(false);
    try {
      await onSent();
      setSending(false);
      change(false);
    } catch {
      setSending(false);
      setSendError(true);
    }
  };

  return <>
    <Button onClick={start} disabled={disabled}><Send aria-hidden />{t("handover.actions.sendToClient")}</Button>
    <Dialog open={open} onOpenChange={change}>
      <DialogContent className="sm:max-w-lg">
        <DialogTitle>{k("title")}</DialogTitle>
        <DialogDescription>{k("description", { owner })}</DialogDescription>
        <ol className="handover-send-steps">
          <li>
            <span className="handover-send-step-label">{k("step1")}</span>
            {url ? (
              <div className="flex gap-2">
                <Input id={urlId} aria-label={t("handover.link.urlLabel")} value={url} readOnly onFocus={(event) => event.currentTarget.select()} className="font-mono text-xs" />
                <Button size="sm" onClick={() => void copy()}><Copy aria-hidden />{t("handover.link.copy")}</Button>
              </div>
            ) : create.isError ? (
              <InlineNotice tone="error" title={t("handover.link.error")} action={<Button size="sm" variant="outline" onClick={prepare}>{k("retry")}</Button>} />
            ) : (
              <p className="inline-flex items-center gap-2 text-xs text-muted-foreground" role="status"><Loader2 aria-hidden className="size-3.5 animate-spin motion-reduce:animate-none" />{k("creating")}</p>
            )}
          </li>
          <li><span className="handover-send-step-label">{k("step2", { owner })}</span></li>
          <li><span className="handover-send-step-label">{k("step3")}</span></li>
        </ol>
        {hadLink && <InlineNotice tone="warning" title={k("replaces")} />}
        {sendError && <InlineNotice tone="error" title={t("handover.done.error")} />}
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={sending} onClick={() => change(false)}>{k("cancel")}</Button>
          <Button disabled={!url || sending} onClick={() => void confirm()}>{k("confirm")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  </>;
}

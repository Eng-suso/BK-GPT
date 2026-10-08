import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/ui/dialog";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Textarea } from "@/ui/textarea";
import { InlineNotice } from "@/components/feedback/InlineNotice";
import { HttpError, httpErrorMessage } from "@/lib/http";
import { useCreateReviewAction } from "./api";
import type { ReviewActionKind, ReviewNode } from "./reviewModel";

export function ReviewActionDialog({ processId, node, revision, kind, initialTitle, initialDetail, returnTarget, onClose, onSaved, onRefresh, onReturnFocus }: {
  processId: string; node: ReviewNode; revision: string; kind: ReviewActionKind;
  initialTitle?: string; initialDetail?: string; returnTarget?: HTMLButtonElement | null;
  onClose: () => void; onSaved: () => void; onRefresh: () => void; onReturnFocus: () => void;
}) {
  const { t } = useTranslation("process");
  const inputId = useId();
  const detailId = useId();
  const [title, setTitle] = useState((initialTitle ?? (kind === "candidate" ? "" : t(`review.defaultTitle.${kind}`, { name: node.name }))).slice(0, 180));
  const [detail, setDetail] = useState((initialDetail ?? "").slice(0, 4000));
  const [requestId] = useState(() => crypto.randomUUID());
  const returnFocus = useRef(returnTarget ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null));
  const mutation = useCreateReviewAction(processId);
  const conflict = mutation.error instanceof HttpError && mutation.error.status === 409;
  return <Dialog open onOpenChange={open => { if (!open && !mutation.isPending) onClose(); }}>
    <DialogContent className="sm:max-w-lg" onCloseAutoFocus={event => { event.preventDefault(); requestAnimationFrame(() => { if (returnFocus.current?.isConnected) returnFocus.current.focus({ preventScroll: true }); else onReturnFocus(); }); }} onEscapeKeyDown={event => { if (mutation.isPending) event.preventDefault(); }} onPointerDownOutside={event => { if (mutation.isPending) event.preventDefault(); }}>
      <DialogTitle>{t(`review.action.${kind}`)}</DialogTitle>
      <DialogDescription>{t(`review.actionDescription.${kind}`, { name: node.name })}</DialogDescription>
      {initialDetail && initialDetail.length > 4000 && <p className="text-xs text-muted-foreground">{t("review.agent.draftTrimmed")}</p>}
      <form className="grid gap-4" onSubmit={event => {
        event.preventDefault();
        if (mutation.isPending || !title.trim() || !detail.trim() || conflict) return;
        mutation.mutate({ id: requestId, node_id: node.id, base_revision: revision, kind, title: title.trim(), detail: detail.trim() }, { onSuccess: onSaved });
      }}>
        <div className="grid gap-1.5"><label htmlFor={inputId} className="text-xs font-medium">{t("review.proposalTitle")}</label><Input id={inputId} value={title} onChange={event => setTitle(event.target.value)} maxLength={180} required disabled={mutation.isPending} /></div>
        <div className="grid gap-1.5"><label htmlFor={detailId} className="text-xs font-medium">{t(`review.detailLabel.${kind}`)}</label><Textarea id={detailId} value={detail} onChange={event => setDetail(event.target.value)} maxLength={4000} rows={5} required disabled={mutation.isPending} placeholder={t(`review.detailPlaceholder.${kind}`)} /></div>
        {mutation.isError && <InlineNotice tone="error" title={conflict ? t("review.staleTitle") : t("review.saveError")} action={conflict ? <Button type="button" variant="outline" size="sm" onClick={() => { onRefresh(); onClose(); }}>{t("review.refresh")}</Button> : undefined}>{conflict ? t("review.staleDescription") : httpErrorMessage(mutation.error, t("review.saveError"))}</InlineNotice>}
        <div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={mutation.isPending} onClick={onClose}>{t("review.cancel")}</Button><Button type="submit" disabled={mutation.isPending || conflict || !title.trim() || !detail.trim()}>{t(mutation.isPending ? "review.saving" : "review.saveAction")}</Button></div>
      </form>
    </DialogContent>
  </Dialog>;
}

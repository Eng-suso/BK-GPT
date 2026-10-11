import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { InlineNotice } from "@/components/feedback/InlineNotice";
import { httpErrorMessage } from "@/lib/http";
import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/ui/dialog";
import { Input } from "@/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/ui/select";
import { Textarea } from "@/ui/textarea";
import { useCreateReviewAction } from "../review/api";
import type { ReviewNode } from "../review/reviewModel";

/**
 * Il responsabile non modifica il disegno: lascia una richiesta su
 * un'attivita'. Diventa una domanda nel registro della revisione, che il
 * consulente trova accanto alle altre.
 */
export function RequestChangesDialog({ processId, revision, nodes, open, onOpenChange, onSaved }: {
  processId: string;
  revision: string;
  nodes: ReviewNode[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => Promise<void> | void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const nodeId = useId();
  const titleId = useId();
  const detailId = useId();
  const [node, setNode] = useState("");
  const [title, setTitle] = useState("");
  const [detail, setDetail] = useState("");
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const mutation = useCreateReviewAction(processId);
  const canSubmit = Boolean(node && title.trim() && detail.trim()) && !mutation.isPending;

  const close = (next: boolean) => {
    if (mutation.isPending) return;
    if (!next) {
      setNode(""); setTitle(""); setDetail(""); setRequestId(crypto.randomUUID()); mutation.reset();
    }
    onOpenChange(next);
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <DialogTitle>{t("handover.request.title")}</DialogTitle>
        <DialogDescription>{t("handover.request.description")}</DialogDescription>
        {nodes.length === 0 ? (
          <InlineNotice tone="warning" title={t("handover.request.noActivities")} />
        ) : (
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (!canSubmit) return;
              mutation.mutate(
                { id: requestId, node_id: node, base_revision: revision, kind: "clarification", title: title.trim(), detail: detail.trim() },
                { onSuccess: async () => { await onSaved(); close(false); } },
              );
            }}
          >
            <div className="grid gap-1.5">
              <label htmlFor={nodeId} className="text-xs font-medium">{t("handover.request.activity")}</label>
              <Select value={node} onValueChange={setNode} disabled={mutation.isPending}>
                <SelectTrigger id={nodeId} className="w-full"><SelectValue placeholder={t("handover.request.pickActivity")} /></SelectTrigger>
                <SelectContent>
                  {nodes.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <label htmlFor={titleId} className="text-xs font-medium">{t("handover.request.titleLabel")}</label>
              <Input id={titleId} value={title} onChange={(event) => setTitle(event.target.value)} maxLength={180} required disabled={mutation.isPending} placeholder={t("handover.request.titlePlaceholder")} />
            </div>
            <div className="grid gap-1.5">
              <label htmlFor={detailId} className="text-xs font-medium">{t("handover.request.detailLabel")}</label>
              <Textarea id={detailId} value={detail} onChange={(event) => setDetail(event.target.value)} maxLength={4000} rows={5} required disabled={mutation.isPending} />
            </div>
            {mutation.isError && <InlineNotice tone="error" title={t("handover.done.error")}>{httpErrorMessage(mutation.error, t("handover.done.error"))}</InlineNotice>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" disabled={mutation.isPending} onClick={() => close(false)}>{t("handover.request.cancel")}</Button>
              <Button type="submit" disabled={!canSubmit}>{t("handover.request.submit")}</Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

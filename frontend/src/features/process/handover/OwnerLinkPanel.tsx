import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Copy, Eye, Link2, Link2Off, RefreshCw } from "lucide-react";

import { ConfirmDialog } from "@/components/feedback";
import { InlineNotice } from "@/components/feedback/InlineNotice";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Skeleton } from "@/ui/skeleton";
import { Surface } from "@/ui/surface";
import { ownerLinkUrl, useCreateOwnerLink, useOwnerLink, useRevokeOwnerLink } from "./ownerDashboardApi";
import { formatDay } from "./useHandoverData";

/**
 * Il link con cui il responsabile del processo apre il cruscotto. Il server ne
 * conserva solo l'impronta: il link si vede una volta, appena creato. Dopo, il
 * consulente vede da quando e' attivo, quando scade e se il cliente l'ha aperto.
 */
export function OwnerLinkPanel({ processId }: { processId: string }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const k = (key: string, options?: Record<string, unknown>) => t(`handover.link.${key}`, options);
  const day = (value: string | null | undefined) => formatDay(value, i18n.language);
  const urlId = useId();
  const status = useOwnerLink(processId);
  const create = useCreateOwnerLink(processId);
  const revoke = useRevokeOwnerLink(processId);
  const [fresh, setFresh] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"renew" | "revoke" | null>(null);
  const busy = create.isPending || revoke.isPending;

  const makeLink = async () => {
    const created = await create.mutateAsync();
    setFresh(ownerLinkUrl(created.token));
  };
  const copy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success(k("copied"));
    } catch {
      // Senza permesso agli appunti il link resta selezionato: si copia a mano.
      document.getElementById(urlId)?.focus();
    }
  };

  const link = status.data;
  return (
    <section className="handover-section" aria-labelledby="handover-link">
      <header className="handover-section-heading"><h2 id="handover-link">{k("title")}</h2><p>{k("description")}</p></header>
      <Surface variant="panel" className="handover-owner">
        {status.isLoading ? <Skeleton className="h-16 w-full" /> : status.isError ? (
          <InlineNotice tone="error" title={k("error")} action={<Button size="sm" variant="outline" onClick={() => void status.refetch()}>{t("handover.dashboard.share.retry")}</Button>} />
        ) : <>
          {fresh && (
            <div className="grid gap-2">
              <label htmlFor={urlId} className="text-xs font-medium">{k("urlLabel")}</label>
              <div className="flex gap-2">
                <Input id={urlId} value={fresh} readOnly onFocus={(event) => event.currentTarget.select()} className="font-mono text-xs" />
                <Button size="sm" onClick={() => void copy(fresh)}><Copy aria-hidden />{k("copy")}</Button>
              </div>
              <InlineNotice tone="warning" title={k("ready")} />
            </div>
          )}
          {link?.active ? (
            <div className="grid gap-1 text-xs text-muted-foreground">
              <p className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-foreground"><Link2 aria-hidden className="size-4" />{k("created", { date: day(link.created_at) })}</p>
              <p>{k("expires", { date: day(link.expires_at) })}</p>
              <p className="inline-flex items-center gap-1.5"><Eye aria-hidden className="size-3.5" />{link.view_count > 0 ? k("viewed", { count: link.view_count, date: day(link.last_viewed_at) }) : k("notViewed")}</p>
            </div>
          ) : !fresh && <p className="text-xs text-muted-foreground">{k("none")}</p>}
          {(create.isError || revoke.isError) && <InlineNotice tone="error" title={k("error")} />}
          <div className="flex flex-wrap gap-2">
            {link?.active ? <>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => setConfirm("renew")}><RefreshCw aria-hidden />{k("renew")}</Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirm("revoke")}><Link2Off aria-hidden />{k("revoke")}</Button>
            </> : (
              <Button size="sm" disabled={busy} onClick={() => void makeLink().catch(() => undefined)}><Link2 aria-hidden />{k("create")}</Button>
            )}
          </div>
        </>}
      </Surface>
      <ConfirmDialog
        open={confirm === "renew"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={k("confirmRenewTitle")}
        description={k("confirmRenewBody")}
        confirmLabel={k("renew")}
        onConfirm={makeLink}
      />
      <ConfirmDialog
        open={confirm === "revoke"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={k("confirmRevokeTitle")}
        description={k("confirmRevokeBody")}
        confirmLabel={k("revoke")}
        destructive
        onConfirm={async () => { await revoke.mutateAsync(); setFresh(null); toast.success(k("revoked")); }}
      />
    </section>
  );
}

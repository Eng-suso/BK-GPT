import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Crosshair, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import type {
  ProcessProvenance,
  ProvenanceElement,
  ProvenanceMarkStatus,
} from "@/contracts/workspace";
import { ErrorState } from "@/components/feedback";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { httpErrorMessage } from "@/lib/http";
import {
  useProcessProvenanceQuery,
  useReviewProvenanceElementMutation,
} from "../api";

type EvidenceReviewPanelProps = {
  processId: string;
  bpmnModelId: string;
  /** Il rifiuto rigenera il disegno: con modifiche locali non salvate si perderebbero. */
  hasUnsavedChanges: boolean;
  /** Porta in vista il nodo dell'elemento; `false` se il disegno non lo contiene. */
  onLocate: (sourceRef: string) => boolean;
  onClose: () => void;
};

const STATUS_TONE: Record<ProvenanceMarkStatus, string> = {
  verified: "border-success-border bg-success-surface text-foreground",
  paraphrased: "border-success-border bg-success-surface text-foreground",
  label_grounded: "border-border bg-muted text-foreground",
  confirmed: "border-border bg-secondary text-secondary-foreground",
  unverified: "border-warning-border bg-warning-surface text-foreground",
};

/**
 * La revisione del disegno elemento per elemento, contro le fonti.
 *
 * Prima cio' che nessuna fonte regge e nessuno ha ancora confermato, perche' e'
 * l'unica cosa su cui il consulente deve agire; poi cio' che ha confermato; poi
 * cio' che le fonti reggono con meno forza; i verificati in fondo e chiusi.
 * Ogni riga mostra il passaggio della fonte che regge l'elemento: e' la prova
 * da rileggere prima di fidarsi del disegno.
 */
export function EvidenceReviewPanel({
  processId,
  bpmnModelId,
  hasUnsavedChanges,
  onLocate,
  onClose,
}: EvidenceReviewPanelProps) {
  const { t } = useTranslation("process");
  const query = useProcessProvenanceQuery(processId);
  const review = useReviewProvenanceElementMutation(processId, bpmnModelId);
  const [pendingReject, setPendingReject] = useState<string | null>(null);
  const [liveMessage, setLiveMessage] = useState("");
  const rowRefs = useRef(new Map<string, HTMLButtonElement>());

  const provenance = query.data;

  if (query.isError && !provenance) {
    return (
      <PanelFrame t={t} onClose={onClose}>
        <ErrorState
          description={httpErrorMessage(query.error, t("canvas.evidence.loadError"))}
          onRetry={() => void query.refetch()}
        />
      </PanelFrame>
    );
  }

  if (!provenance) {
    return (
      <PanelFrame t={t} onClose={onClose}>
        <div className="grid gap-2 p-3" aria-busy="true">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      </PanelFrame>
    );
  }

  if (!provenance.hasPlan) {
    return (
      <PanelFrame t={t} onClose={onClose}>
        <p className="p-3 text-xs leading-relaxed text-muted-foreground">
          {t("canvas.evidence.noPlan")}
        </p>
      </PanelFrame>
    );
  }

  const awaiting = provenance.elements.filter(
    (item) => item.status === "unverified" && item.consultantDecision !== "confirmed",
  );
  const confirmed = provenance.elements.filter((item) => item.markStatus === "confirmed");
  const weak = provenance.elements.filter(
    (item) => item.status === "paraphrased" || item.status === "label_grounded",
  );
  const verified = provenance.elements.filter((item) => item.status === "verified");

  function focusNextAfter(sourceRef: string) {
    const order = awaiting.map((item) => item.sourceRef);
    const next = order[order.indexOf(sourceRef) + 1] ?? order[order.indexOf(sourceRef) - 1];
    // Il focus non si perde nel documento quando la riga su cui si e' deciso
    // sparisce dalla lista: passa alla successiva da rivedere.
    window.setTimeout(() => {
      if (next) rowRefs.current.get(next)?.focus();
    }, 0);
  }

  function decide(item: ProvenanceElement, decision: "confirmed" | "rejected") {
    setPendingReject(null);
    review.mutate(
      { sourceRef: item.sourceRef, decision },
      {
        onSuccess: (result) => {
          setLiveMessage(result.reason);
          if (result.ok) toast.success(result.reason);
          else toast.error(result.reason);
          focusNextAfter(item.sourceRef);
        },
        onError: (error) => {
          const message = httpErrorMessage(error, t("canvas.evidence.reviewError"));
          setLiveMessage(message);
          toast.error(message);
        },
      },
    );
  }

  function locate(item: ProvenanceElement) {
    if (!onLocate(item.sourceRef)) {
      setLiveMessage(t("canvas.evidence.notDrawn", { label: item.label }));
    }
  }

  const reviewingRef = review.isPending ? review.variables?.sourceRef : null;

  const renderRow = (item: ProvenanceElement, actions: boolean) => {
    const busy = reviewingRef === item.sourceRef;
    const rejecting = pendingReject === item.sourceRef;
    return (
      <li key={item.sourceRef} className="grid gap-1.5 border-b border-border px-3 py-2.5 last:border-b-0">
        <div className="flex items-start justify-between gap-2">
          <button
            type="button"
            ref={(node) => {
              if (node) rowRefs.current.set(item.sourceRef, node);
              else rowRefs.current.delete(item.sourceRef);
            }}
            onClick={() => locate(item)}
            className="flex min-w-0 items-start gap-1.5 rounded-sm text-left text-[13px] font-medium text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-ring"
            title={t("canvas.evidence.locate")}
          >
            <Crosshair aria-hidden className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
            <span className="min-w-0 break-words">{item.label || item.elementId}</span>
          </button>
          <span
            className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${STATUS_TONE[item.markStatus]}`}
          >
            {t(`canvas.evidence.status.${item.markStatus}`)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className="text-[10px] uppercase tracking-wide">
            {t(`canvas.evidence.kind.${item.kind}`)}
          </Badge>
          {item.sourceName && (
            <span className="truncate text-[11px] text-muted-foreground">{item.sourceName}</span>
          )}
        </div>
        {item.quote ? (
          <blockquote className="border-l-2 border-border pl-2 text-xs leading-relaxed text-muted-foreground">
            {item.quote}
          </blockquote>
        ) : (
          <p className="text-xs leading-relaxed text-muted-foreground">
            {t("canvas.evidence.noQuote")}
          </p>
        )}
        {actions && (
          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={review.isPending}
              onClick={() => decide(item, "confirmed")}
              aria-label={t("canvas.evidence.confirmLabel", { label: item.label })}
            >
              <Check aria-hidden className="size-3.5" />
              {busy && review.variables?.decision === "confirmed"
                ? t("canvas.evidence.saving")
                : t("canvas.evidence.confirm")}
            </Button>
            {item.removable && (
              <Button
                type="button"
                size="sm"
                variant={rejecting ? "destructive" : "ghost"}
                disabled={review.isPending || hasUnsavedChanges}
                onClick={() =>
                  rejecting ? decide(item, "rejected") : setPendingReject(item.sourceRef)
                }
                aria-label={
                  rejecting
                    ? t("canvas.evidence.rejectConfirmLabel", { label: item.label })
                    : t("canvas.evidence.rejectLabel", { label: item.label })
                }
              >
                <Trash2 aria-hidden className="size-3.5" />
                {busy && review.variables?.decision === "rejected"
                  ? t("canvas.evidence.redrawing")
                  : rejecting
                    ? t("canvas.evidence.rejectConfirm")
                    : t("canvas.evidence.reject")}
              </Button>
            )}
            {rejecting && (
              <Button type="button" size="sm" variant="ghost" onClick={() => setPendingReject(null)}>
                {t("canvas.evidence.cancel")}
              </Button>
            )}
          </div>
        )}
        {actions && item.removable && hasUnsavedChanges && (
          <p className="text-[11px] text-muted-foreground">{t("canvas.evidence.saveFirst")}</p>
        )}
        {actions && !item.removable && (
          <p className="text-[11px] text-muted-foreground">{t("canvas.evidence.notRemovable")}</p>
        )}
      </li>
    );
  };

  return (
    <PanelFrame t={t} onClose={onClose} snapshotLabel={provenance.snapshotLabel}>
      <p className="sr-only" role="status" aria-live="polite">
        {liveMessage}
      </p>
      <Summary provenance={provenance} awaiting={awaiting.length} t={t} />
      {provenance.unusedSources.length > 0 && (
        <p className="mx-3 mb-2 rounded-md border border-warning-border bg-warning-surface px-2.5 py-2 text-xs leading-relaxed text-foreground">
          {t("canvas.evidence.unusedSources", { sources: provenance.unusedSources.join(", ") })}
        </p>
      )}

      <Section title={t("canvas.evidence.sections.awaiting")} count={awaiting.length}>
        {awaiting.length === 0 ? (
          <p className="px-3 py-2 text-xs text-muted-foreground">{t("canvas.evidence.nothingAwaiting")}</p>
        ) : (
          <ul>{awaiting.map((item) => renderRow(item, true))}</ul>
        )}
      </Section>
      {confirmed.length > 0 && (
        <Section title={t("canvas.evidence.sections.confirmed")} count={confirmed.length}>
          <ul>{confirmed.map((item) => renderRow(item, false))}</ul>
        </Section>
      )}
      {weak.length > 0 && (
        <Section title={t("canvas.evidence.sections.weak")} count={weak.length}>
          <ul>{weak.map((item) => renderRow(item, false))}</ul>
        </Section>
      )}
      {verified.length > 0 && (
        <details className="border-t border-border">
          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-foreground focus-visible:outline-2 focus-visible:outline-ring">
            {t("canvas.evidence.sections.verified")} ({verified.length})
          </summary>
          <ul>{verified.map((item) => renderRow(item, false))}</ul>
        </details>
      )}
    </PanelFrame>
  );
}

type TFunction = ReturnType<typeof useTranslation>["t"];

function PanelFrame({
  t,
  onClose,
  snapshotLabel,
  children,
}: {
  t: TFunction;
  onClose: () => void;
  snapshotLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <aside className="process-evidence-panel" aria-labelledby="process-evidence-title">
      <header className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
        <div className="min-w-0">
          <h3 id="process-evidence-title" className="text-sm font-semibold text-foreground">
            {t("canvas.evidence.title")}
          </h3>
          {snapshotLabel && (
            <p className="text-[11px] text-muted-foreground">
              {t("canvas.evidence.plan", { label: snapshotLabel })}
            </p>
          )}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          onClick={onClose}
          aria-label={t("canvas.evidence.close")}
          title={t("canvas.evidence.close")}
        >
          <X />
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
    </aside>
  );
}

function Summary({
  provenance,
  awaiting,
  t,
}: {
  provenance: ProcessProvenance;
  awaiting: number;
  t: TFunction;
}) {
  return (
    <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 px-3 py-2.5 text-xs">
      <dt className="text-muted-foreground">{t("canvas.evidence.summary.grounded")}</dt>
      <dd className="text-right font-medium tabular-nums text-foreground">
        {Math.round(provenance.groundedRatio * 100)}%
      </dd>
      <dt className="text-muted-foreground">{t("canvas.evidence.summary.verified")}</dt>
      <dd className="text-right tabular-nums text-foreground">{provenance.verified}</dd>
      <dt className="text-muted-foreground">{t("canvas.evidence.summary.weak")}</dt>
      <dd className="text-right tabular-nums text-foreground">
        {provenance.paraphrased + provenance.labelGrounded}
      </dd>
      <dt className="text-muted-foreground">{t("canvas.evidence.summary.awaiting")}</dt>
      <dd className="text-right font-medium tabular-nums text-foreground">{awaiting}</dd>
      <dt className="text-muted-foreground">{t("canvas.evidence.summary.sources")}</dt>
      <dd className="text-right tabular-nums text-foreground">{provenance.sourcesChecked}</dd>
    </dl>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-border">
      <h4 className="px-3 pt-2.5 pb-1 text-xs font-semibold text-foreground">
        {title} <span className="font-normal tabular-nums text-muted-foreground">({count})</span>
      </h4>
      {children}
    </section>
  );
}

import { useTranslation } from "react-i18next";
import { CheckCircle2, CircleDashed, RefreshCw, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import type { ConformanceArea, ConformanceFinding, ConformanceStatus } from "@/contracts/workspace";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { httpErrorMessage } from "@/lib/http";
import { useConformanceStatusQuery, useRunConformanceAuditMutation } from "../api";

/** L'ordine in cui il consulente legge i punti: prima cio' che cambia il disegno. */
const AREA_ORDER: ConformanceArea[] = [
  "source_contradiction",
  "source_coverage",
  "plan_currency",
  "review_plan",
  "canvas_plan",
];

type Tone = "ok" | "attention" | "neutral";

const TONE_CLASS: Record<Tone, string> = {
  ok: "border-success-border bg-success-surface",
  attention: "border-warning-border bg-warning-surface",
  neutral: "border-border bg-muted",
};

/**
 * Il confronto fra disegno, piano e fonti, come lo legge un consulente.
 *
 * Una risposta sola in alto - coincide, da rivedere, non ancora confrontato - e
 * sotto i punti raggruppati per cosa significano per il disegno. Gli elementi
 * senza riscontro nelle fonti non si ripetono qui: hanno gia' la loro sezione,
 * con le azioni per confermarli o toglierli.
 */
export function ConformanceSummary({ processId }: { processId: string }) {
  const { t } = useTranslation("process");
  const query = useConformanceStatusQuery(processId);
  const audit = useRunConformanceAuditMutation(processId);

  function runAudit() {
    audit.mutate(undefined, {
      onSuccess: (status) => {
        const verdict = status.report?.verdict;
        if (verdict === "conformant") toast.success(t("canvas.conformance.toast.conformant"));
        else toast.message(t("canvas.conformance.toast.done"));
      },
      onError: (error) => {
        toast.error(httpErrorMessage(error, t("canvas.conformance.runError")));
      },
    });
  }

  const status = query.data;

  return (
    <section className="grid gap-2 border-b border-border px-3 py-2.5" aria-labelledby="process-conformance-title">
      <div className="flex items-center justify-between gap-2">
        <h4 id="process-conformance-title" className="text-xs font-semibold text-foreground">
          {t("canvas.conformance.title")}
        </h4>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={runAudit}
          disabled={audit.isPending || !status}
          aria-busy={audit.isPending}
        >
          <RefreshCw aria-hidden className={`size-3.5 ${audit.isPending ? "animate-spin" : ""}`} />
          {audit.isPending ? t("canvas.conformance.running") : t("canvas.conformance.run")}
        </Button>
      </div>

      {query.isError && !status ? (
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t("canvas.conformance.loadError")}{" "}
          <button
            type="button"
            className="font-medium text-foreground underline focus-visible:outline-2 focus-visible:outline-ring"
            onClick={() => void query.refetch()}
          >
            {t("canvas.conformance.retry")}
          </button>
        </p>
      ) : !status ? (
        <div className="grid gap-1.5" aria-busy="true">
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <StatusBody status={status} running={audit.isPending} />
      )}
    </section>
  );
}

type TFunction = ReturnType<typeof useTranslation>["t"];

function StatusBody({ status, running }: { status: ConformanceStatus; running: boolean }) {
  const { t, i18n } = useTranslation("process");
  const report = status.report;

  if (running) {
    return (
      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("canvas.conformance.runningHint")}
      </p>
    );
  }

  if (!report) {
    return (
      <Verdict tone="neutral" icon={<CircleDashed aria-hidden className="size-4 text-muted-foreground" />}>
        <p className="text-[13px] font-medium text-foreground">{t("canvas.conformance.verdict.none")}</p>
        <p className="text-xs text-muted-foreground">{t("canvas.conformance.noneHint")}</p>
      </Verdict>
    );
  }

  const listed = report.findings.filter((item) => item.area !== "plan_sources");
  const withoutSource = report.findings.length - listed.length;
  const auditedAt = formatDate(report.auditedAt, i18n.language);

  return (
    <div className="grid gap-2">
      {report.verdict === "conformant" ? (
        <Verdict tone="ok" icon={<CheckCircle2 aria-hidden className="size-4 text-[var(--color-status-success)]" />}>
          <p className="text-[13px] font-medium text-foreground">{t("canvas.conformance.verdict.conformant")}</p>
          <p className="text-xs text-muted-foreground">
            {t("canvas.conformance.checkedOn", { count: report.sourcesAudited, date: auditedAt })}
          </p>
        </Verdict>
      ) : report.verdict === "not_conformant" ? (
        <Verdict tone="attention" icon={<TriangleAlert aria-hidden className="size-4 text-[var(--color-status-warning)]" />}>
          <p className="text-[13px] font-medium text-foreground">
            {t("canvas.conformance.verdict.notConformant", { count: report.findings.length })}
          </p>
          <p className="text-xs text-muted-foreground">
            {t("canvas.conformance.checkedOn", { count: report.sourcesAudited, date: auditedAt })}
          </p>
        </Verdict>
      ) : (
        <Verdict tone="neutral" icon={<CircleDashed aria-hidden className="size-4 text-muted-foreground" />}>
          <p className="text-[13px] font-medium text-foreground">{t("canvas.conformance.verdict.incomplete")}</p>
          {report.note && <p className="text-xs text-muted-foreground">{capitalize(report.note)}</p>}
        </Verdict>
      )}

      {!status.isCurrent && (
        <p className="rounded-md border border-border bg-muted px-2 py-1.5 text-[11px] leading-relaxed text-foreground">
          {t("canvas.conformance.outdated")}
        </p>
      )}

      {AREA_ORDER.map((area) => {
        const items = listed.filter((item) => item.area === area);
        return items.length ? <FindingGroup key={area} area={area} items={items} t={t} /> : null;
      })}

      {withoutSource > 0 && (
        <p className="text-xs leading-relaxed text-muted-foreground">
          {t("canvas.conformance.withoutSource", { count: withoutSource })}
        </p>
      )}
    </div>
  );
}

function Verdict({ tone, icon, children }: { tone: Tone; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className={`flex items-start gap-2 rounded-md border px-2.5 py-2 ${TONE_CLASS[tone]}`}>
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="grid min-w-0 gap-0.5">{children}</div>
    </div>
  );
}

function FindingGroup({ area, items, t }: { area: ConformanceArea; items: ConformanceFinding[]; t: TFunction }) {
  return (
    <details className="rounded-md border border-border" open={area === "source_contradiction"}>
      <summary className="cursor-pointer px-2.5 py-1.5 text-xs font-semibold text-foreground focus-visible:outline-2 focus-visible:outline-ring">
        {t(`canvas.conformance.area.${area}`)}{" "}
        <span className="font-normal tabular-nums text-muted-foreground">({items.length})</span>
      </summary>
      <ul className="border-t border-border">
        {items.map((item, index) => (
          <li
            key={`${area}-${index}`}
            className="border-b border-border px-2.5 py-2 text-xs leading-relaxed text-foreground last:border-b-0"
          >
            {item.message}
          </li>
        ))}
      </ul>
    </details>
  );
}

function formatDate(value: string, language: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(language, { dateStyle: "short", timeStyle: "short" }).format(date);
}

function capitalize(value: string): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

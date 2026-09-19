import { useTranslation } from "react-i18next";
import { CheckCircle2, CircleDashed, Loader2, RefreshCw, TriangleAlert, Wand2 } from "lucide-react";
import { toast } from "sonner";

import type { ConformanceArea, ConformanceFinding, ConformanceStatus } from "@/contracts/workspace";
import { Button } from "@/ui/button";
import { Skeleton } from "@/ui/skeleton";
import { httpErrorMessage } from "@/lib/http";
import {
  useConformanceStatusQuery,
  useRepairFromConformanceMutation,
  useRunConformanceAuditMutation,
} from "../api";

/** L'ordine in cui il consulente legge i punti: prima cio' che cambia il disegno. */
const AREA_ORDER: ConformanceArea[] = [
  "source_contradiction",
  "source_coverage",
  "source_divergence",
  "plan_currency",
  "review_plan",
  "canvas_plan",
];

/** I punti che una rilettura delle fonti puo' chiudere davvero. */
const REPAIRABLE: ConformanceArea[] = ["source_coverage", "source_contradiction"];

type Tone = "ok" | "attention" | "neutral";

const TONE_CLASS: Record<Tone, string> = {
  ok: "border-success-border bg-success-surface",
  attention: "border-warning-border bg-warning-surface",
  neutral: "border-border bg-muted",
};

type ConformanceSummaryProps = {
  processId: string;
  bpmnModelId: string;
};

/**
 * Il confronto fra disegno, piano e fonti, come lo legge un consulente.
 *
 * Il confronto non blocca il disegno: parte quando il canvas viene salvato e
 * gira dietro, quindi questo pannello ha tre stati veri - in corso, un esito,
 * nessun esito ancora - e non li confonde mai fra loro. I punti sono
 * raggruppati per cosa significano per il disegno; quelli che una rilettura
 * delle fonti puo' chiudere hanno il bottone che li integra, ed e' il consulente
 * a premerlo: il disegno non cambia da solo sotto i suoi occhi.
 *
 * Gli elementi senza riscontro nelle fonti non si ripetono qui: hanno gia' la
 * loro sezione, con le azioni per confermarli o toglierli.
 */
export function ConformanceSummary({ processId, bpmnModelId }: ConformanceSummaryProps) {
  const { t } = useTranslation("process");
  const query = useConformanceStatusQuery(processId);
  const audit = useRunConformanceAuditMutation(processId);
  const repair = useRepairFromConformanceMutation(processId, bpmnModelId);

  const status = query.data;
  const busy = audit.isPending || repair.isPending || Boolean(status?.running);

  function runAudit() {
    audit.mutate(undefined, {
      onSuccess: (result) => {
        const verdict = result.report?.verdict;
        if (verdict === "conformant") toast.success(t("canvas.conformance.toast.conformant"));
        else toast.message(t("canvas.conformance.toast.done"));
      },
      onError: (error) => toast.error(httpErrorMessage(error, t("canvas.conformance.runError"))),
    });
  }

  function runRepair() {
    repair.mutate(undefined, {
      onSuccess: () => toast.success(t("canvas.conformance.toast.repaired")),
      onError: (error) => toast.error(httpErrorMessage(error, t("canvas.conformance.repairError"))),
    });
  }

  return (
    <section
      className="grid gap-2 border-b border-border px-3 py-2.5"
      aria-labelledby="process-conformance-title"
    >
      <div className="flex items-center justify-between gap-2">
        <h4 id="process-conformance-title" className="text-xs font-semibold text-foreground">
          {t("canvas.conformance.title")}
        </h4>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={runAudit}
          disabled={busy || !status}
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
        <StatusBody
          status={status}
          working={audit.isPending || repair.isPending}
          repairing={repair.isPending}
          onRepair={runRepair}
        />
      )}
    </section>
  );
}

type TFunction = ReturnType<typeof useTranslation>["t"];

function StatusBody({
  status,
  working,
  repairing,
  onRepair,
}: {
  status: ConformanceStatus;
  working: boolean;
  repairing: boolean;
  onRepair: () => void;
}) {
  const { t, i18n } = useTranslation("process");
  const report = status.report;

  if (working || status.running) {
    return (
      <Verdict tone="neutral" icon={<Loader2 aria-hidden className="size-4 animate-spin text-muted-foreground" />}>
        <p className="text-[13px] font-medium text-foreground">
          {repairing ? t("canvas.conformance.repairing") : t("canvas.conformance.inProgress")}
        </p>
        <p className="text-xs text-muted-foreground">
          {repairing ? t("canvas.conformance.repairingHint") : t("canvas.conformance.inProgressHint")}
        </p>
      </Verdict>
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
  const repairable = listed.filter((item) => REPAIRABLE.includes(item.area)).length;
  const checkedOn = t("canvas.conformance.checkedOn", {
    count: report.sourcesAudited,
    date: formatDate(report.auditedAt, i18n.language),
  });

  return (
    <div className="grid gap-2">
      {report.verdict === "conformant" ? (
        <Verdict tone="ok" icon={<CheckCircle2 aria-hidden className="size-4 text-[var(--color-status-success)]" />}>
          <p className="text-[13px] font-medium text-foreground">
            {t("canvas.conformance.verdict.conformant")}
          </p>
          <p className="text-xs text-muted-foreground">{checkedOn}</p>
        </Verdict>
      ) : report.verdict === "conformant_with_divergences" ? (
        <Verdict tone="ok" icon={<CheckCircle2 aria-hidden className="size-4 text-[var(--color-status-success)]" />}>
          <p className="text-[13px] font-medium text-foreground">
            {t("canvas.conformance.verdict.withDivergences", { count: report.findings.length })}
          </p>
          <p className="text-xs text-muted-foreground">{checkedOn}</p>
        </Verdict>
      ) : report.verdict === "not_conformant" ? (
        <Verdict
          tone="attention"
          icon={<TriangleAlert aria-hidden className="size-4 text-[var(--color-status-warning)]" />}
        >
          <p className="text-[13px] font-medium text-foreground">
            {t("canvas.conformance.verdict.notConformant", { count: report.findings.length })}
          </p>
          <p className="text-xs text-muted-foreground">{checkedOn}</p>
        </Verdict>
      ) : (
        <Verdict tone="neutral" icon={<CircleDashed aria-hidden className="size-4 text-muted-foreground" />}>
          <p className="text-[13px] font-medium text-foreground">
            {t("canvas.conformance.verdict.incomplete")}
          </p>
          {report.note && <p className="text-xs text-muted-foreground">{capitalize(report.note)}</p>}
        </Verdict>
      )}

      {!status.isCurrent && (
        <p className="rounded-md border border-border bg-muted px-2 py-1.5 text-[11px] leading-relaxed text-foreground">
          {t("canvas.conformance.outdated")}
        </p>
      )}

      {AREA_ORDER.filter((area) => listed.some((item) => item.area === area)).map(
        (area, index) => (
          <FindingGroup
            key={area}
            area={area}
            items={listed.filter((item) => item.area === area)}
            // Il primo gruppo e' aperto: il punto piu' importante si legge
            // senza doverlo cercare, gli altri restano a portata di un clic.
            defaultOpen={index === 0}
            t={t}
          />
        ),
      )}

      {repairable > 0 && (
        <div className="grid gap-1">
          <Button type="button" size="sm" variant="secondary" onClick={onRepair} disabled={repairing}>
            <Wand2 aria-hidden className="size-3.5" />
            {t("canvas.conformance.repair", { count: repairable })}
          </Button>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {t("canvas.conformance.repairHint")}
          </p>
        </div>
      )}

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

function FindingGroup({
  area,
  items,
  defaultOpen,
  t,
}: {
  area: ConformanceArea;
  items: ConformanceFinding[];
  defaultOpen: boolean;
  t: TFunction;
}) {
  return (
    <details className="rounded-md border border-border" open={defaultOpen}>
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

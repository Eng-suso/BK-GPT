import React from "react";
import { useTranslation } from "react-i18next";
import { Link2, X } from "lucide-react";

import { Button } from "@/ui/button";

import { formatParameterDuration } from "./studio/activityParameters";
import type { ClaimProposal } from "./simulationTypes";
import type { TaskDraft } from "./simulationScenario";

/**
 * Le affermazioni dei file del cliente proposte come fonte della durata (SIM-07).
 * Il consulente collega o scarta ogni proposta: una collegata diventa la fonte
 * dichiarata del parametro, e una durata citata resta un riferimento.
 */
export function ActivitySources({
  elementId,
  taskName,
  task,
  proposals,
  dismissed,
  onChange,
  onDismiss,
}: {
  elementId: string;
  taskName: string;
  task: TaskDraft;
  proposals: ClaimProposal[];
  dismissed: number[];
  onChange: (next: TaskDraft) => void;
  onDismiss: (claimId: number) => void;
}): React.JSX.Element | null {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language.startsWith("it") ? "it" : "en";
  const linked = task.claims ?? [];
  const linkedIds = new Set(linked.map((c) => c.claimId));
  const open = proposals.filter((p) => !linkedIds.has(p.claim_id) && !dismissed.includes(p.claim_id));
  if (linked.length === 0 && open.length === 0) return null;
  const byId = new Map(proposals.map((p) => [p.claim_id, p]));
  const headingId = `sim-sources-${elementId}`;
  // Il nome accessibile cita l'affermazione: due proposte dello stesso file restano distinguibili.
  const short = (text: string) => (text.length > 80 ? `${text.slice(0, 77)}…` : text);

  const reference = (proposal: ClaimProposal | undefined) => proposal?.duration_hint && (
    <span className="block text-xs text-muted-foreground">
      {t("simulation.config.sourceSays", { duration: formatParameterDuration(proposal.duration_hint.seconds, lang), text: proposal.duration_hint.text })}
    </span>
  );

  return (
    <div className="sim-task-sources mt-3 grid gap-2 border-t border-border pt-3">
      <p id={headingId} className="text-xs font-medium text-foreground">{t("simulation.config.sources")}</p>
      <p className="text-xs text-muted-foreground">{t("simulation.config.sourcesHint")}</p>
      <ul aria-labelledby={headingId} className="grid gap-2">
        {linked.map((claim) => {
          const proposal = byId.get(claim.claimId);
          return (
            <li key={claim.claimId} data-linked-claim={claim.claimId} className="grid gap-1 rounded-md border border-border bg-card p-2.5">
              <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <Link2 aria-hidden className="size-3.5" />{t("simulation.config.sourceLinked", { file: claim.label })}
              </span>
              {proposal && <q className="text-sm text-foreground">{proposal.statement}</q>}
              {reference(proposal)}
              <Button type="button" size="sm" variant="ghost" className="justify-self-start"
                aria-label={t("simulation.config.unlinkSourceFor", { task: taskName, what: proposal ? short(proposal.statement) : claim.label })}
                onClick={() => onChange({ ...task, claims: linked.filter((c) => c.claimId !== claim.claimId) })}>
                {t("simulation.config.unlinkSource")}
              </Button>
            </li>
          );
        })}
        {open.map((proposal) => (
          <li key={proposal.claim_id} data-proposed-claim={proposal.claim_id} className="grid gap-1 rounded-md border border-dashed border-border p-2.5">
            <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.sourceProposed", { file: proposal.source_name })}</span>
            <q className="text-sm text-foreground">{proposal.statement}</q>
            {reference(proposal)}
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" variant="outline"
                aria-label={t("simulation.config.linkSourceFor", { task: taskName, what: short(proposal.statement) })}
                onClick={() => onChange({ ...task, claims: [...linked, { claimId: proposal.claim_id, label: proposal.source_name }] })}>
                <Link2 aria-hidden className="size-3.5" />{t("simulation.config.linkSource")}
              </Button>
              <Button type="button" size="sm" variant="ghost"
                aria-label={t("simulation.config.dismissSourceFor", { task: taskName, what: short(proposal.statement) })}
                onClick={() => onDismiss(proposal.claim_id)}>
                <X aria-hidden className="size-3.5" />{t("simulation.config.dismissSource")}
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

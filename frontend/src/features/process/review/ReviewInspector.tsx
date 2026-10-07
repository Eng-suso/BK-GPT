import { ArrowDownLeft, ArrowUpRight, ChevronLeft, ChevronRight, CircleHelp, FileOutput, GitBranch, ListChecks, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";
import { Badge } from "@/ui/badge";
import { Surface } from "@/ui/surface";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/ui/tabs";
import { InlineNotice } from "@/components/feedback/InlineNotice";
import type { ProcessProvenance } from "@/contracts/workspace";
import { inspectReviewNode, type ReviewGraph, type ReviewNode, type ReviewState } from "./reviewModel";
import { ReviewMascot } from "./ReviewMascot";

export function ReviewInspector({ node, graph, state, provenance, evidenceError, evidenceLoading, onRetryEvidence, tab, onTab, onSelect, onSimulation }: {
  node: ReviewNode; graph: ReviewGraph; state: ReviewState; provenance?: ProcessProvenance;
  evidenceError: boolean; evidenceLoading: boolean; onRetryEvidence: () => void;
  tab: string; onTab: (tab: string) => void;
  onSelect: (id: string) => void; onSimulation: () => void;
}) {
  const { t } = useTranslation("process");
  const inspection = inspectReviewNode(node, graph, state, provenance);
  const { owner, inputs, outputs, gaps, scope } = inspection;
  const actions = state.actions.filter(action => action.node_id === node.id);
  const index = graph.nodes.findIndex(task => task.id === node.id);
  const suggestion = gaps.length ? t(`review.suggestionFor.${gaps[0]}`) : t("review.suggestionComplete");
  const value = (text: string) => text || t("review.notDocumented");
  return <div className="review-inspector-content">
    <div className="review-dossier-heading">
      <div className="review-dossier-position"><span>{t("review.task")} <b>{String(index + 1).padStart(2, "0")}</b><span className="review-position-total"> / {String(graph.nodes.length).padStart(2, "0")}</span></span><div className="flex gap-1"><Button size="icon-sm" variant="ghost" aria-label={t("review.previousTask")} disabled={index <= 0} onClick={() => onSelect(graph.nodes[index - 1].id)}><ChevronLeft aria-hidden /></Button><Button size="icon-sm" variant="ghost" aria-label={t("review.nextTask")} disabled={index >= graph.nodes.length - 1} onClick={() => onSelect(graph.nodes[index + 1].id)}><ChevronRight aria-hidden /></Button></div></div>
      <h3>{node.name}</h3><div className="review-dossier-status"><span className={gaps.length ? "review-status-dot review-status-dot--pending" : "review-status-dot"} aria-hidden />{t(gaps.length ? "review.needsReview" : "review.documented")}{actions[0] && <Badge variant="outline">{t(`review.kind.${actions[0].kind}`)}</Badge>}</div>
    </div>
    <Tabs value={tab} onValueChange={onTab}>
      <TabsList variant="line" className="review-dossier-tabs w-full" aria-label={t("review.detailTabs")}>
        {(["overview", "evidence", "impacts", "actions"] as const).map(name => <TabsTrigger key={name} value={name} className="px-1.5 text-xs">{t(`review.tab.${name}`)}</TabsTrigger>)}
      </TabsList>
      <TabsContent value="overview" className="space-y-4 pt-3">
        <dl className="review-node-facts">
          <div className="review-fact-owner"><dt>{t("review.field.owner")}</dt><dd><span className="review-owner-monogram" aria-hidden>{owner ? owner.split(/\s+/).slice(0, 2).map(word => word[0]).join("").toLocaleUpperCase() : "—"}</span><span>{value(owner)}</span></dd></div>
          <Surface asChild variant="inset"><div className="review-fact-transfer"><dt><ArrowDownLeft aria-hidden />{t("review.field.input")}</dt><dd className={!inputs.length ? "review-missing-value" : undefined}>{value(inputs.join(", "))}</dd></div></Surface>
          <Surface asChild variant="inset"><div className="review-fact-transfer"><dt><FileOutput aria-hidden />{t("review.field.output")}</dt><dd className={!outputs.length ? "review-missing-value" : undefined}>{value(outputs.join(", "))}</dd></div></Surface>
          <div className="review-fact-issues" data-pending={gaps.length > 0}><dt><CircleHelp aria-hidden />{t("review.field.problems")}<span className="review-issue-count">{String(gaps.length).padStart(2, "0")}</span></dt><dd>{gaps.length ? <ul className="space-y-1">{gaps.map(gap => <li key={gap}>{t(`review.gap.${gap}`)}</li>)}</ul> : t("review.noStructuralGaps")}</dd></div>
          <div className="review-fact-scope"><dt><GitBranch aria-hidden />{t("review.field.impacts")}</dt><dd><div className="review-scope-path"><span><b>{scope.upstream.length}</b>{t("review.upstream")}</span><i aria-hidden /><span className="review-scope-current" role="img" aria-label={`${t("review.selected")}: ${node.name}`} /><i aria-hidden /><span><b>{scope.downstream.length}</b>{t("review.downstream")}</span></div><Button variant="link" size="sm" className="h-auto px-0 py-1" onClick={() => onTab("impacts")}>{t("review.exploreImpacts")}<ArrowUpRight aria-hidden /></Button></dd></div>
          <div className="review-fact-suggestion"><dt><ReviewMascot />{t("review.field.suggestion")}</dt><dd>{suggestion}</dd></div>
        </dl>
        {node.notes && <Surface variant="inset" className="p-3"><p className="mb-1 text-xs font-semibold">{t("review.taskNotes")}</p><p className="whitespace-pre-wrap text-xs leading-relaxed">{node.notes}</p></Surface>}
        {!state.plan && <InlineNotice tone="warning" title={t("review.noPlan")}>{t("review.noPlanDescription")}</InlineNotice>}
      </TabsContent>
      <TabsContent value="evidence" className="space-y-3 pt-3">
        {evidenceError ? <InlineNotice tone="error" title={t("review.evidenceError")} action={<Button size="sm" variant="outline" onClick={onRetryEvidence}>{t("review.retry")}</Button>} /> : evidenceLoading ? <p role="status" className="text-xs text-muted-foreground">{t("review.loadingEvidence")}</p> : inspection.evidence.length ? inspection.evidence.map(evidence => <Surface key={evidence.sourceRef} variant="inset" className="space-y-2 p-3">
          <div className="flex flex-wrap items-center gap-2"><Badge variant="outline">{t(`canvas.evidence.status.${evidence.markStatus}`)}</Badge></div>
          <p className="text-xs font-medium">{evidence.sourceName || t("review.noSource")}</p>
          {evidence.quote ? <blockquote className="border-l-2 border-border pl-3 text-xs leading-relaxed">{evidence.quote}</blockquote> : <p className="text-xs text-muted-foreground">{t("review.noQuote")}</p>}
        </Surface>) : <InlineNotice tone="warning" title={t("review.noEvidence")}>{t("review.noEvidenceDescription")}</InlineNotice>}
      </TabsContent>
      <TabsContent value="impacts" className="space-y-4 pt-3">
        <InlineNotice title={t("review.dependencyTitle")}>{t("review.dependencyDescription")}</InlineNotice>
        {(["upstream", "downstream"] as const).map(direction => <section key={direction}><h4 className="mb-2 flex items-center gap-2 text-xs font-semibold">{direction === "upstream" ? <ArrowDownLeft aria-hidden className="size-4" /> : <ArrowUpRight aria-hidden className="size-4" />}{t(`review.${direction}`)} <Badge variant="secondary">{scope[direction].length}</Badge></h4>{scope[direction].length ? <div className="space-y-1">{scope[direction].map(task => <Button key={task.id} variant="ghost" size="sm" className="h-auto w-full justify-start whitespace-normal py-2 text-left text-xs" onClick={() => onSelect(task.id)}>{task.name}</Button>)}</div> : <p className="text-xs text-muted-foreground">{t("review.noDependencies")}</p>}</section>)}
        <section><h4 className="mb-2 flex items-center gap-2 text-xs font-semibold"><ShieldCheck aria-hidden className="size-4" />{t("review.controls")}</h4><p className="text-xs leading-relaxed">{value(inspection.controls.map(control => control.label).join(" · "))}</p></section>
        <section><h4 className="mb-2 flex items-center gap-2 text-xs font-semibold"><ListChecks aria-hidden className="size-4" />{t("review.rules")}</h4><p className="text-xs leading-relaxed">{value(inspection.rules.map(rule => `${rule.label}: ${rule.consequence}`).join(" · "))}</p></section>
        <section><h4 className="mb-2 flex items-center gap-2 text-xs font-semibold"><FileOutput aria-hidden className="size-4" />{t("review.documents")}</h4><p className="text-xs leading-relaxed">{value([...inputs, ...outputs].join(" · "))}</p></section>
        <Surface variant="inset" className="space-y-2 p-3"><h4 className="text-xs font-semibold">{t("review.performanceTitle")}</h4><p className="text-xs leading-relaxed text-muted-foreground">{t("review.performanceDescription")}</p><Button variant="outline" size="sm" onClick={onSimulation}>{t("review.openSimulation")}</Button></Surface>
      </TabsContent>
      <TabsContent value="actions" className="space-y-3 pt-3">
        <p className="text-xs leading-relaxed text-muted-foreground">{t("review.actionsDescription")}</p>
        {actions.length ? actions.map(action => <Surface key={action.id} variant="inset" className="space-y-2 p-3"><Badge variant="outline">{t(`review.kind.${action.kind}`)}</Badge><h4 className="text-xs font-semibold break-words">{action.title}</h4><p className="whitespace-pre-wrap break-words text-xs leading-relaxed">{action.detail}</p>{action.base_revision !== state.base_revision && <p className="text-xs font-medium text-warning">{t("review.staleAction")}</p>}</Surface>) : <p className="text-xs text-muted-foreground">{t("review.noActions")}</p>}
      </TabsContent>
    </Tabs>
  </div>;
}

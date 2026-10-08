import React from "react";
import { ArrowRight, Check, Focus, GitBranch, ListFilter, LockKeyhole, RefreshCw, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CanvasWorkspaceShell, WorkspaceCommandBar, WorkspaceDisclosure, WorkspaceInspector } from "@/components/layout/CanvasWorkspace";
import { Button } from "@/ui/button";
import { Badge } from "@/ui/badge";
import { Surface } from "@/ui/surface";
import { Input } from "@/ui/input";
import { Skeleton } from "@/ui/skeleton";
import { InlineNotice } from "@/components/feedback/InlineNotice";
import { useElementWidth } from "@/lib/useElementWidth";
import { useProcessProvenanceQuery } from "../api";
import { useImpactReview } from "./api";
import { inspectReviewNode, readReviewGraph, type ReviewActionKind, type ReviewNode } from "./reviewModel";
import { ReviewCanvas } from "./ReviewCanvas";
import { ReviewInspector } from "./ReviewInspector";
import { ReviewActionDialog } from "./ReviewActionDialog";
import { ReviewActions } from "./ReviewActions";
import { ReviewHypotheses } from "./ReviewHypotheses";
import { ReviewAgent } from "./ReviewAgent";
import { ReviewProposalViewer } from "./ReviewProposalViewer";
import type { ReviewAction } from "./reviewModel";
import "./review.css";

export function ProcessReviewWorkspace({ projectId, processName, processId, bpmnModelId, mode, onModeChange, onSimulation }: {
  projectId: string; processName: string; processId: string; bpmnModelId: string; mode: "review" | "tobe";
  onModeChange: (mode: "canvas" | "review" | "tobe") => void; onSimulation: () => void;
}) {
  const { t } = useTranslation("process");
  const query = useImpactReview(processId, bpmnModelId);
  const evidence = useProcessProvenanceQuery(processId);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = React.useState(false);
  const [focusImpact, setFocusImpact] = React.useState(true);
  const [tab, setTab] = React.useState("overview");
  const [search, setSearch] = React.useState("");
  const [action, setAction] = React.useState<{ kind: ReviewActionKind; node: ReviewNode; revision: string; initialTitle?: string; initialDetail?: string; returnTarget?: HTMLButtonElement | null } | null>(null);
  const [agentRequest, setAgentRequest] = React.useState<{ id: number; prompt: string } | null>(null);
  const [preview, setPreview] = React.useState<ReviewAction | null>(null);
  const [saved, setSaved] = React.useState(false);
  const [listOpen, setListOpen] = React.useState(false);
  const { ref, width } = useElementWidth<HTMLDivElement>();
  const lastSelection = React.useRef<HTMLButtonElement | null>(null);
  const tasksButton = React.useRef<HTMLButtonElement | null>(null);
  const inspector = React.useRef<HTMLElement | null>(null);
  const graph = React.useMemo(() => {
    try { return readReviewGraph(query.data?.xml ?? null); } catch { return null; }
  }, [query.data?.xml]);
  const selected = graph?.nodes.find(node => node.id === selectedId) ?? null;
  const inspection = selected && graph && query.data ? inspectReviewNode(selected, graph, query.data, evidence.isError ? undefined : evidence.data) : null;
  const selectNode = (id: string) => { setSelectedId(id); setAgentRequest(null); setSaved(false); };
  const closeInspector = () => {
    setInspectorOpen(false);
    requestAnimationFrame(() => {
      const last = lastSelection.current;
      const target = last?.isConnected ? last : tasksButton.current;
      target?.focus({ preventScroll: true });
    });
  };
  const compact = width > 0 && width < 980;
  React.useLayoutEffect(() => {
    if (inspectorOpen && selected && compact) inspector.current?.querySelector<HTMLElement>("[data-dock-title]")?.focus();
  }, [inspectorOpen, selected, compact]);

  // Keep the measured root mounted while query states change so ResizeObserver
  // also starts during the initial loading render.
  if (query.isError) return <div ref={ref} className="process-review-workspace"><div className="p-4"><InlineNotice tone="error" title={t("review.loadError")} action={<Button variant="outline" size="sm" onClick={() => void query.refetch()}>{t("review.retry")}</Button>} /></div></div>;
  if (!query.data) return <div ref={ref} className="process-review-workspace"><div className="grid h-full grid-cols-1 gap-3 p-4" aria-label={t("review.loading")}><Skeleton className="h-10" /><Skeleton className="min-h-80" /></div></div>;
  const state = query.data;
  const candidates = state.actions.filter(item => item.kind === "candidate");
  const allTasks = graph?.nodes ?? [];
  const askAgent = (prompt: string) => { setInspectorOpen(false); setAgentRequest({ id: Date.now(), prompt }); };
  const filteredTasks = allTasks.filter(node => node.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));

  if (mode === "tobe") return <div ref={ref} className="process-review-workspace"><ReviewHypotheses state={state} onReturn={() => onModeChange("review")} onPreview={setPreview} onInspect={id => { selectNode(id); setInspectorOpen(true); setTab("actions"); onModeChange("review"); }} />{preview && <ReviewProposalViewer action={preview} baseline={state.xml} onClose={() => setPreview(null)} />}</div>;

  return <div ref={ref} className="process-review-workspace">
    <CanvasWorkspaceShell label={t("review.title")} className="p-2" bodyClassName={compact && inspectorOpen && selected ? "review-body-compact" : ""} commands={<WorkspaceCommandBar material="floating" label={t("review.commands")} className={compact ? "review-commands-compact" : undefined}>
      <div className="review-command-context mr-auto flex min-w-0 items-center gap-2 text-muted-foreground"><LockKeyhole aria-hidden className="size-3.5" /><span className="text-xs">{t("review.asIsReadOnly")}</span></div>
      <Button ref={tasksButton} variant="ghost" size="sm" aria-pressed={listOpen} onClick={() => setListOpen(value => !value)}><ListFilter aria-hidden />{t("review.tasks")} <span className="tabular-nums">{allTasks.length}</span></Button>
      <Button variant="ghost" size={compact ? "icon" : "sm"} aria-label={t("review.focusImpact")} title={t("review.focusImpact")} aria-pressed={focusImpact} onClick={() => setFocusImpact(value => !value)}><GitBranch aria-hidden /><span className="review-command-label">{t("review.focusImpact")}</span></Button>
      <WorkspaceDisclosure label={t(compact ? "review.more" : "review.processFindings")}>
        <p className="mb-3 text-xs text-muted-foreground">{t("review.findingsScope")}</p>{state.plan?.consultant_findings.length ? state.plan.consultant_findings.map(finding => <div key={finding.id} className="mb-3 border-b border-border pb-3 text-xs leading-relaxed"><p className="font-medium">{finding.finding}</p>{finding.recommendation && <p className="mt-1 text-muted-foreground">{finding.recommendation}</p>}</div>) : <p className="text-xs text-muted-foreground">{t("review.noFindings")}</p>}
      </WorkspaceDisclosure>
      <Button variant="ghost" size="icon" aria-label={t("review.refresh")} onClick={() => { void query.refetch(); void evidence.refetch(); }}><RefreshCw aria-hidden /></Button>
      <Button variant="outline" size={compact ? "icon" : "sm"} aria-label={t("review.hypotheses")} title={t("review.hypotheses")} onClick={() => onModeChange("tobe")}><span className="review-command-label">{t("review.hypotheses")}</span>{!compact && <Badge variant="secondary">{candidates.length}</Badge>}<ArrowRight aria-hidden /></Button>
    </WorkspaceCommandBar>} inspector={selected && inspectorOpen && graph && <WorkspaceInspector ref={inspector} label={t("review.inspector")} title={t("review.inspector")} closeLabel={t("review.closeInspector")} onClose={closeInspector} resizeLabel={compact ? undefined : t("actions.resizeInspector")} minimumStageWidth={520} initialWidth={400} maximumWidth={480} className={compact ? "review-inspector-compact" : "review-inspector"} bodyClassName="review-dossier-body" footer={<ReviewActions onAgent={() => askAgent("")} onPropose={target => askAgent(t(`review.agent.prompt.${target}`))} onAction={kind => setAction({ kind, node: selected, revision: state.base_revision })} />}>
      <ReviewInspector node={selected} graph={graph} state={state} provenance={evidence.isError ? undefined : evidence.data} evidenceError={evidence.isError} evidenceLoading={evidence.isPending} onRetryEvidence={() => void evidence.refetch()} tab={tab} onTab={setTab} onSelect={selectNode} onSimulation={onSimulation} onPreview={setPreview} onAskAgent={() => askAgent(t("review.agent.prompt.opinion"))} />
    </WorkspaceInspector>}>
      <div className={`review-stage-content ${compact && inspectorOpen && selected ? "review-stage-content--covered" : ""}`}>
        {graph && state.xml && allTasks.length ? <ReviewCanvas xml={state.xml} nodes={allTasks} selected={selected} upstream={inspection?.scope.upstream.map(node => node.id) ?? []} downstream={inspection?.scope.downstream.map(node => node.id) ?? []} documents={inspection?.scope.documents ?? []} focusImpact={focusImpact} onSelect={selectNode} renderAgent={anchor => <ReviewAgent node={selected} projectId={projectId} processId={processId} processName={processName} bpmnModelId={bpmnModelId} revision={state.base_revision} anchor={anchor} request={agentRequest} onDetails={() => { setInspectorOpen(true); setTab("overview"); }} onPropose={(kind, detail, returnTarget) => { if (selected) setAction({ kind, node: selected, revision: state.base_revision, initialTitle: t("review.agent.proposalFor", { name: selected.name }), initialDetail: detail, returnTarget }); }} onSimulation={onSimulation} onChooseTask={() => setListOpen(true)} />} /> : <div className="review-empty"><Focus aria-hidden className="size-6 text-muted-foreground" /><h3 className="text-sm font-semibold">{t(graph ? "review.emptyTitle" : "review.diagramError")}</h3><p className="max-w-sm text-center text-xs leading-relaxed text-muted-foreground">{t("review.emptyDescription")}</p><Button size="sm" variant="outline" onClick={() => onModeChange("canvas")}>{t("review.openAsIs")}</Button></div>}

        {graph && allTasks.length > 0 && !selected && <Surface variant="floating" className="review-start-hint"><Focus aria-hidden className="size-4 text-primary" /><p className="text-xs">{t("review.selectHint")}</p></Surface>}
        {listOpen && <Surface variant="floating" className="review-task-list ui-scrollbar" role="region" aria-label={t("review.taskList")}>
          <div className="mb-3 flex items-center gap-2"><Search aria-hidden className="size-4 text-muted-foreground" /><Input value={search} onChange={event => setSearch(event.target.value)} placeholder={t("review.searchTasks")} aria-label={t("review.searchTasks")} className="h-9" /></div>
          <div className="space-y-1">{filteredTasks.map(node => <Button key={node.id} variant="ghost" className="h-auto min-h-11 w-full justify-start whitespace-normal py-2 text-left text-xs" aria-pressed={node.id === selectedId} onClick={event => { lastSelection.current = event.currentTarget; selectNode(node.id); setListOpen(false); }}><span>{node.name}</span>{node.id === selectedId && <Check aria-hidden className="ml-auto shrink-0" />}</Button>)}{!filteredTasks.length && <p className="text-xs text-muted-foreground">{t("review.noSearchResults")}</p>}</div>
        </Surface>}
        {selected && focusImpact && <div className="review-impact-legend" role="group" aria-label={t("review.impactLegend")}><span><i className="review-legend-upstream" aria-hidden />{t("review.upstream")}</span><span><i className="review-legend-selected" aria-hidden />{t("review.selected")}</span><span><i className="review-legend-downstream" aria-hidden />{t("review.downstream")}</span></div>}
      </div>
    </CanvasWorkspaceShell>
    {preview && <ReviewProposalViewer action={preview} baseline={state.xml} onClose={() => setPreview(null)} />}
    {saved && <div className="review-save-feedback" role="status"><Check aria-hidden className="size-4" />{t("review.actionSaved")}</div>}
    {action && <ReviewActionDialog key={`${action.node.id}:${action.kind}`} processId={processId} node={action.node} revision={action.revision} kind={action.kind} initialTitle={action.initialTitle} initialDetail={action.initialDetail} returnTarget={action.returnTarget} onClose={() => setAction(null)} onSaved={() => { setAction(null); setSaved(true); setTab("actions"); }} onRefresh={() => void query.refetch()} onReturnFocus={() => inspector.current?.querySelector<HTMLElement>("[data-dock-title]")?.focus()} />}
  </div>;
}

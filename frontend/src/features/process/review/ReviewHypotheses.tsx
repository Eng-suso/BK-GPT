import { ArrowLeft, ArrowUpRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { WorkspaceCommandBar } from "@/components/layout/CanvasWorkspace";
import { Button } from "@/ui/button";
import { Surface } from "@/ui/surface";
import { InlineNotice } from "@/components/feedback/InlineNotice";
import { ReviewMascot } from "./ReviewMascot";
import type { ReviewState, ReviewAction } from "./reviewModel";

export function ReviewHypotheses({ state, onReturn, onInspect, onPreview }: {
  state: ReviewState; onReturn: () => void; onInspect: (id: string) => void; onPreview: (action: ReviewAction) => void;
}) {
  const { t, i18n } = useTranslation("process");
  const candidates = state.actions.filter(action => action.kind === "candidate" || action.kind === "as_is_proposal");
  const taskCount = new Set(candidates.map(action => action.node_id)).size;
  const date = (value: string) => {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "" : new Intl.DateTimeFormat(i18n.language, { day: "numeric", month: "short", year: "numeric" }).format(parsed);
  };
  return <section className="review-hypotheses ui-scrollbar" aria-label={t("review.hypothesesTitle")}>
    <WorkspaceCommandBar material="floating" className="m-2" label={t("review.hypothesesTitle")}><Button variant="ghost" size="sm" onClick={onReturn}><ArrowLeft aria-hidden />{t("review.backToReview")}</Button><span className="ml-auto text-xs text-muted-foreground">{t("review.candidateCount", { count: candidates.length })}</span></WorkspaceCommandBar>
    <div className="review-proposal-register">
      <header className="review-register-heading"><div><p className="review-register-context">As-Is <span aria-hidden> / </span> Review <span aria-hidden> / </span> To-Be</p><h2>{t("review.proposalBoard")}</h2><p>{t("review.proposalBoardDescription")}</p></div><span className="review-register-total" aria-label={t("review.candidateCount", { count: candidates.length })}>{String(candidates.length).padStart(2, "0")}</span></header>
      {candidates.length > 0 && <p className="review-register-summary">{t("review.candidateTaskCount", { count: taskCount })}<span aria-hidden> · </span>{t("review.pendingDecision")}</p>}
      <ol className="review-proposal-list">{candidates.map((item, index) => <li key={item.id}><Surface asChild variant="panel"><article className="review-proposal-record">
        <div className="review-proposal-index" aria-hidden>{String(index + 1).padStart(2, "0")}</div>
        <div className="review-proposal-content"><div className="review-proposal-context"><span>{item.node_name}</span><span>{t(`review.kind.${item.kind}`)}</span></div><h3>{item.title}</h3><p className="review-proposal-detail">{item.detail}</p>{item.base_revision !== state.base_revision && <InlineNotice className="mt-3" tone="warning" title={t("review.staleAction")} />}<footer className="review-proposal-footer"><time dateTime={item.created_at}>{date(item.created_at)}</time>{item.proposal_xml && <Button variant="outline" size="sm" onClick={() => onPreview(item)}>{t("review.agent.preview")}</Button>}<Button variant="ghost" size="sm" onClick={() => onInspect(item.node_id)}>{t("review.openTask")}<ArrowUpRight aria-hidden /></Button></footer></div>
      </article></Surface></li>)}</ol>
      {!candidates.length && <Surface variant="inset" className="review-register-empty"><ReviewMascot /><div><h3>{t("review.noCandidates")}</h3><p>{t("review.noCandidatesDescription")}</p><Button variant="link" size="sm" onClick={onReturn}>{t("review.startReview")}<ArrowUpRight aria-hidden /></Button></div></Surface>}
      <p className="review-register-note">{t("review.hypothesesDescription")}</p>
    </div>
  </section>;
}

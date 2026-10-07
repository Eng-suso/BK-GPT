import { ArrowUpRight, BookOpen, Clock3, MessageSquarePlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";
import type { ReviewActionKind } from "./reviewModel";

/** One decision area shared by all inspector tabs, outside the scroll region. */
export function ReviewActions({ onEvidence, onAction }: {
  onEvidence: () => void; onAction: (kind: ReviewActionKind) => void;
}) {
  const { t } = useTranslation("process");
  return <div className="review-decision-actions">
    <Button onClick={() => onAction("candidate")} className="review-propose"><span>{t("review.action.candidate")}</span><ArrowUpRight aria-hidden /></Button>
    <div className="review-secondary-actions">
      <Button variant="ghost" size="sm" aria-label={t("review.showEvidence")} title={t("review.showEvidence")} onClick={onEvidence}><BookOpen aria-hidden />{t("review.shortAction.evidence")}</Button>
      <Button variant="ghost" size="sm" aria-label={t("review.action.clarification")} title={t("review.action.clarification")} onClick={() => onAction("clarification")}><MessageSquarePlus aria-hidden />{t("review.shortAction.clarification")}</Button>
      <Button variant="ghost" size="sm" aria-label={t("review.action.deferred")} title={t("review.action.deferred")} onClick={() => onAction("deferred")}><Clock3 aria-hidden />{t("review.shortAction.deferred")}</Button>
    </div>
  </div>;
}

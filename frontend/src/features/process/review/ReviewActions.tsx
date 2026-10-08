import { ArrowUpRight, Clock3, MessageSquare, MessageSquarePlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";
import type { ReviewActionKind } from "./reviewModel";

/** Operational actions: conversation first, proposals stay separate from baseline. */
export function ReviewActions({ onAgent, onPropose, onAction }: {
  onAgent: () => void; onPropose: (target: "asIs" | "toBe") => void; onAction: (kind: ReviewActionKind) => void;
}) {
  const { t } = useTranslation("process");
  return <div className="review-decision-actions">
    <Button onClick={onAgent} className="review-propose"><MessageSquare aria-hidden /><span>{t("review.agent.workTogether")}</span><ArrowUpRight aria-hidden /></Button>
    <div className="review-proposal-actions"><Button variant="outline" size="sm" onClick={() => onPropose("asIs")}>{t("review.agent.asIs")}</Button><Button variant="outline" size="sm" onClick={() => onPropose("toBe")}>{t("review.agent.toBe")}</Button></div>
    <div className="review-secondary-actions">
      <Button variant="ghost" size="sm" onClick={() => onAction("clarification")}><MessageSquarePlus aria-hidden />{t("review.shortAction.clarification")}</Button>
      <Button variant="ghost" size="sm" onClick={() => onAction("deferred")}><Clock3 aria-hidden />{t("review.shortAction.deferred")}</Button>
    </div>
  </div>;
}

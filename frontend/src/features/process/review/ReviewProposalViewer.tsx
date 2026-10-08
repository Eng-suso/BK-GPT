import { useState } from "react";
import { Download } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/ui/dialog";
import { Button } from "@/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/ui/tabs";
import { ReviewCanvas } from "./ReviewCanvas";
import { readReviewGraph, type ReviewAction, type ReviewNode } from "./reviewModel";

export function ReviewProposalViewer({ action, baseline, onClose }: { action: ReviewAction; baseline: string | null; onClose: () => void }) {
  const { t } = useTranslation("process");
  const [version, setVersion] = useState("proposal");
  const xml = version === "baseline" ? baseline : action.proposal_xml;
  const download = () => {
    if (!action.proposal_xml) return;
    const url = URL.createObjectURL(new Blob([action.proposal_xml], { type: "application/xml" }));
    const link = document.createElement("a"); link.href = url; link.download = `review-${action.id}.bpmn`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  let nodes: ReviewNode[];
  try { nodes = readReviewGraph(xml ?? null).nodes; } catch { nodes = []; }
  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}><DialogContent className="review-proposal-viewer sm:max-w-5xl">
    <DialogTitle>{action.title}</DialogTitle><DialogDescription>{t("review.agent.separateProposal")}</DialogDescription>
    <Tabs value={version} onValueChange={setVersion} className="flex min-h-0 flex-1 flex-col gap-3"><div className="flex flex-wrap items-center justify-between gap-2"><TabsList><TabsTrigger value="baseline">{t("review.agent.baseline")}</TabsTrigger><TabsTrigger value="proposal">{t(`review.kind.${action.kind}`)}</TabsTrigger></TabsList><Button variant="outline" size="sm" onClick={download}><Download aria-hidden />{t("review.agent.download")}</Button></div>
    <TabsContent value={version} className="mt-0 min-h-0 flex-1">{xml && <ReviewCanvas xml={xml} nodes={nodes} selected={null} upstream={[]} downstream={[]} documents={[]} focusImpact={false} onSelect={() => {}} />}</TabsContent></Tabs>
    <p className="max-h-24 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">{action.detail}</p>
  </DialogContent></Dialog>;
}

import { useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";
import { Surface } from "@/ui/surface";
import type { ReviewNode } from "./reviewModel";

export function ReviewTaskNavigator({ nodes, selectedId, onSelect }: {
  nodes: ReviewNode[]; selectedId: string | null;
  onSelect: (id: string, trigger: HTMLButtonElement) => void;
}) {
  const { t } = useTranslation("process");
  const ribbon = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    const element = ribbon.current;
    if (!element) return;
    const reveal = () => {
      const active = element.querySelector<HTMLButtonElement>('[aria-current="step"]');
      if (!active) return;
      const frame = element.getBoundingClientRect();
      const item = active.getBoundingClientRect();
      element.scrollLeft += item.left - frame.left - (element.clientWidth - active.offsetWidth) / 2;
    };
    reveal();
    const observer = new ResizeObserver(reveal);
    observer.observe(element);
    return () => observer.disconnect();
  }, [selectedId]);
  return <Surface variant="floating" asChild><nav ref={ribbon} className="review-task-ribbon ui-scrollbar" aria-label={t("review.navigateTasks")}>{nodes.map((node, index) => <Button key={node.id} variant="ghost" className="review-task-stop" aria-label={t("review.selectTask", { position: index + 1, name: node.name })} aria-current={node.id === selectedId ? "step" : undefined} onClick={event => onSelect(node.id, event.currentTarget)}><span className="review-task-number" aria-hidden>{String(index + 1).padStart(2, "0")}</span><span className="review-task-name">{node.name}</span></Button>)}</nav></Surface>;
}

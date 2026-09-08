import React from "react";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, MessageSquareText } from "lucide-react";

import { Button } from "@/ui/button";

import type { ChatScope } from "../chatScope";

interface EmptyStateProps {
  scope?: ChatScope;
  onSelectPrompt?: (prompt: string) => void;
}

/** Flow nodes that mean "someone has already modelled something here". */
const MODELLED_ELEMENT = /<bpmn:(task|userTask|serviceTask|manualTask|scriptTask|sendTask|receiveTask|businessRuleTask|callActivity|subProcess|exclusiveGateway|parallelGateway|inclusiveGateway|eventBasedGateway)\b/;

/**
 * Whether the canvas already carries a model the consultant can be asked about.
 *
 * A new process opens on an empty diagram (see `buildInitialProcessDiagram`),
 * and suggesting edits to a model that does not exist invents the model.
 */
function canvasIsModelled(scope?: ChatScope): boolean {
  if (scope?.type !== "canvas") return false;
  return MODELLED_ELEMENT.test(scope.currentBpmnXml ?? "");
}

/**
 * Scope-aware intro: says what this assistant does here and offers a few
 * ready-to-send prompts. Kept as a quiet in-panel block — not a centered hero —
 * so it reads like a work surface, not a landing page.
 *
 * The prompts never name domain content — no "the credit check", no invented
 * activity. A suggestion the consultant did not describe is a claim about the
 * client's process that no source backs, and reading it is enough to plant it.
 * They talk about the *workspace* (evidence, sources, roles, layout) and let
 * the client's own vocabulary come from the model and the sources.
 */
export const EmptyState: React.FC<EmptyStateProps> = ({
  scope,
  onSelectPrompt,
}) => {
  const { t } = useTranslation("chat");
  const key = scope?.type ?? "consultant";

  const title = t(`scope.${key}.title`);
  const description = t(`scope.${key}.description`);
  const promptsKey = canvasIsModelled(scope)
    ? `scope.${key}.promptsModeled`
    : `scope.${key}.prompts`;
  const prompts = t(promptsKey, { returnObjects: true });
  const promptList = Array.isArray(prompts) ? (prompts as string[]) : [];

  return (
    <div className="welcome mx-auto flex h-full max-w-md flex-col justify-center px-4 py-8">
      <div className="flex items-center gap-2.5">
        <MessageSquareText
          className="size-5 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
        <p className="text-[15px] font-semibold text-foreground text-balance">
          {title}
        </p>
      </div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground text-pretty">
        {description}
      </p>

      {promptList.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.04em] text-muted-foreground">
            {t("empty.tryLabel")}
          </p>
          <ul className="flex flex-col gap-1">
            {promptList.map((prompt) => (
              <li key={prompt}>
                <Button
                  variant="outline"
                  type="button"
                  onClick={() => onSelectPrompt?.(prompt)}
                  disabled={!onSelectPrompt}
                  className="group flex h-auto min-h-10 w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-[13px] font-normal whitespace-normal"
                >
                  <span className="min-w-0">{prompt}</span>
                  <ArrowUpRight className="size-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

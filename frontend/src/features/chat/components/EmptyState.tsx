import React from "react";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, MessageSquareText } from "lucide-react";

import type { ChatScope } from "../chatScope";

interface EmptyStateProps {
  scope?: ChatScope;
  onSelectPrompt?: (prompt: string) => void;
}

/**
 * Scope-aware welcome: says what this assistant does here and offers a few
 * ready-to-send prompts, so the consultant is never staring at a blank box.
 */
export const EmptyState: React.FC<EmptyStateProps> = ({
  scope,
  onSelectPrompt,
}) => {
  const { t } = useTranslation("chat");
  const key = scope?.type ?? "consultant";

  const title = t(`scope.${key}.title`);
  const description = t(`scope.${key}.description`);
  const prompts = t(`scope.${key}.prompts`, { returnObjects: true });
  const promptList = Array.isArray(prompts) ? (prompts as string[]) : [];

  return (
    <div className="welcome flex h-full flex-col items-center justify-center px-6 py-8 text-center">
      <div className="welcome-inner mx-auto flex w-full max-w-md flex-col items-center">
        <div
          className="mb-4 grid size-11 place-items-center rounded-xl bg-primary/10 text-primary"
          aria-hidden="true"
        >
          <MessageSquareText className="size-5" />
        </div>
        <h1 className="m-0 text-lg font-semibold tracking-tight text-foreground text-balance">
          {title}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground text-pretty">
          {description}
        </p>

        {promptList.length > 0 && (
          <div className="mt-6 w-full">
            <p className="eyebrow mb-2 text-left">{t("empty.tryLabel")}</p>
            <ul className="flex flex-col gap-1.5">
              {promptList.map((prompt) => (
                <li key={prompt}>
                  <button
                    type="button"
                    onClick={() => onSelectPrompt?.(prompt)}
                    disabled={!onSelectPrompt}
                    className="group flex w-full items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2 text-left text-[13px] text-foreground transition-colors hover:border-primary/40 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
                  >
                    <span className="min-w-0">{prompt}</span>
                    <ArrowUpRight className="size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};

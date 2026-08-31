import React from "react";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, MessageSquareText } from "lucide-react";

import type { ChatScope } from "../chatScope";

interface EmptyStateProps {
  scope?: ChatScope;
  onSelectPrompt?: (prompt: string) => void;
}

/**
 * Scope-aware intro: says what this assistant does here and offers a few
 * ready-to-send prompts. Kept as a quiet in-panel block — not a centered hero —
 * so it reads like a work surface, not a landing page.
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
                <button
                  type="button"
                  onClick={() => onSelectPrompt?.(prompt)}
                  disabled={!onSelectPrompt}
                  className="group flex w-full items-center justify-between gap-3 rounded-md border border-border bg-card px-3 py-2 text-left text-[13px] text-foreground transition-colors hover:border-primary/40 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
                >
                  <span className="min-w-0">{prompt}</span>
                  <ArrowUpRight className="size-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

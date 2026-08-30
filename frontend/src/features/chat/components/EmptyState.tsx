import React from "react";
import { MessageSquareText } from "lucide-react";

interface EmptyStateProps {
  onSelectPrompt?: (prompt: string) => void;
}

export const EmptyState: React.FC<EmptyStateProps> = () => {
  return (
    <div className="welcome flex h-full items-center justify-center px-4 py-6 text-center">
      <div className="welcome-inner mx-auto w-[min(calc(100%-48px),1040px)]">
        <div
          className="mx-auto mb-4 grid size-12 place-items-center rounded-xl bg-primary/10 text-primary"
          aria-hidden="true"
        >
          <MessageSquareText className="size-6" />
        </div>
        <h1 className="m-0 text-xl font-semibold tracking-tight text-foreground">
          Ciao! Come posso aiutarti oggi?
        </h1>
      </div>
    </div>
  );
};

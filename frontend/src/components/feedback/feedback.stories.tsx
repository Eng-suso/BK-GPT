import type { Meta, StoryObj } from "@storybook/react";
import { BarChart3 } from "lucide-react";

import { Button } from "@/ui/button";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";

const meta: Meta = {
  title: "Components/Feedback",
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

export const Empty: Story = {
  render: () => (
    <div className="w-[480px] rounded-xl border border-border bg-card">
      <EmptyState
        title="Nessun processo in scope"
        description="Aggiungi processi dalla chat agente per popolare la roadmap."
        action={
          <Button variant="outline" size="sm">
            Apri chat
          </Button>
        }
      />
    </div>
  ),
};

export const EmptyInline: Story = {
  render: () => (
    <div className="w-[320px] rounded-xl border border-border bg-card p-4">
      <EmptyState
        variant="inline"
        icon={BarChart3}
        title="Non disponibile"
        description="I KPI di progetto non sono ancora tracciati dal backend."
      />
    </div>
  ),
};

export const Error: Story = {
  render: () => (
    <div className="w-[480px] rounded-xl border border-border bg-card">
      <ErrorState onRetry={() => undefined} />
    </div>
  ),
};

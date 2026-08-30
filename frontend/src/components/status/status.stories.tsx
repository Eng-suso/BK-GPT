import type { Meta, StoryObj } from "@storybook/react";

import { PriorityTag } from "./PriorityTag";
import { StatusIndicator } from "./StatusIndicator";

const meta: Meta = {
  title: "Components/Status",
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

export const Statuses: Story = {
  render: () => (
    <div className="flex flex-col gap-3">
      <StatusIndicator tone="ok" label="In corso" />
      <StatusIndicator tone="warning" label="In ritardo" />
      <StatusIndicator tone="danger" label="Bloccato" />
      <StatusIndicator tone="pending" label="Da validare" />
      <StatusIndicator tone="neutral" label="Bozza" />
    </div>
  ),
};

export const Priorities: Story = {
  render: () => (
    <div className="flex items-center gap-2">
      <PriorityTag priority="alta" />
      <PriorityTag priority="media" />
      <PriorityTag priority="bassa" />
    </div>
  ),
};

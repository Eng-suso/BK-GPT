import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import { ResizeHandle } from "./ResizeHandle";

const meta: Meta<typeof ResizeHandle> = {
  title: "Layout/ResizeHandle",
  component: ResizeHandle,
};
export default meta;

function TwoPanelsDemo() {
  const [width, setWidth] = useState(260);
  const [start, setStart] = useState(260);
  return (
    <div className="flex h-[240px] w-[560px] gap-2">
      <div
        className="rounded-md border border-border bg-card p-3 text-sm"
        style={{ width }}
      >
        Left panel — {width}px
      </div>
      <ResizeHandle
        ariaLabel="Resize left panel"
        onResizeStart={() => setStart(width)}
        onDelta={(dx) => setWidth(Math.max(140, Math.min(420, start + dx)))}
      />
      <div className="flex-1 rounded-md border border-border bg-card p-3 text-sm">
        Right panel (flex)
      </div>
    </div>
  );
}

type Story = StoryObj<typeof ResizeHandle>;

export const TwoPanels: Story = {
  render: () => <TwoPanelsDemo />,
};

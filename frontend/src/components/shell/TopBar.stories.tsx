import type { Meta, StoryObj } from "@storybook/react";

import "@/lib/i18n";
import { TopBar } from "./TopBar";

const meta = {
  title: "Shell/TopBar",
  component: TopBar,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof TopBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

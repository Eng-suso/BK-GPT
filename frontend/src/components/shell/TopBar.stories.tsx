import type { Meta, StoryObj } from "@storybook/react";
import { TopBar } from "./TopBar";

const meta = {
  title: "Shell/TopBar",
  component: TopBar,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
  argTypes: {
    activeSection: {
      control: { type: "select" },
      options: ["home", "consultant", "clients", "projects", "models", "archive"],
    },
  },
} satisfies Meta<typeof TopBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Home: Story = {
  args: { activeSection: "home" },
};

export const Clienti: Story = {
  args: { activeSection: "clients" },
};

export const Progetti: Story = {
  args: { activeSection: "projects" },
};

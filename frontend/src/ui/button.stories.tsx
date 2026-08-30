import type { Meta, StoryObj } from "@storybook/react";
import { Plus } from "lucide-react";

import { Button } from "./button";

const meta = {
  title: "UI/Button",
  component: Button,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: "select",
      options: [
        "default",
        "outline",
        "secondary",
        "ghost",
        "destructive",
        "link",
      ],
    },
    size: {
      control: "select",
      options: ["xs", "sm", "default", "lg", "icon", "icon-sm"],
    },
  },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = { args: { children: "Nuovo progetto" } };
export const Outline: Story = {
  args: { variant: "outline", children: "Filtri" },
};
export const Ghost: Story = { args: { variant: "ghost", children: "Ripristina" } };
export const Destructive: Story = {
  args: { variant: "destructive", children: "Elimina" },
};

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-3">
      <Button>
        <Plus /> Nuovo progetto
      </Button>
      <Button variant="outline">Filtri</Button>
      <Button variant="secondary">Secondario</Button>
      <Button variant="ghost">Ripristina</Button>
      <Button variant="destructive">Elimina</Button>
      <Button variant="link">Dettagli</Button>
    </div>
  ),
};

export const Sizes: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-3">
      <Button size="xs">xs</Button>
      <Button size="sm">sm</Button>
      <Button size="default">default</Button>
      <Button size="lg">lg</Button>
    </div>
  ),
};

import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";
import { Plus } from "lucide-react";

import { Button } from "@/ui/button";
import { PageHeader } from "./PageHeader";

const meta = {
  title: "Components/PageHeader",
  component: PageHeader,
  parameters: { layout: "padded" },
  decorators: [
    (Story) => (
      <MemoryRouter>
        <div className="max-w-4xl">
          <Story />
        </div>
      </MemoryRouter>
    ),
  ],
} satisfies Meta<typeof PageHeader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const List: Story = {
  args: {
    breadcrumbs: [{ label: "Progetti", to: "/projects" }, { label: "Portafoglio" }],
    title: "Progetti",
    count: 12,
    description:
      "Monitora lo stato del portafoglio progetti di consulenza e avanza con decisioni informate.",
    actions: (
      <Button size="sm">
        <Plus /> Nuovo progetto
      </Button>
    ),
  },
};

export const Detail: Story = {
  args: {
    breadcrumbs: [
      { label: "Progetti", to: "/projects" },
      { label: "Trasformazione Supply Chain", to: "/projects/1" },
      { label: "Panoramica" },
    ],
    title: "Trasformazione Supply Chain",
    actions: (
      <>
        <Button variant="ghost" size="sm">
          Aggiorna stato
        </Button>
        <Button size="sm">Apri roadmap</Button>
      </>
    ),
  },
};

import type { Meta, StoryObj } from "@storybook/react";
import { PlaceholderPage } from "./PlaceholderPage";

const meta = {
  title: "Shell/PlaceholderPage",
  component: PlaceholderPage,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
  argTypes: {
    items: { control: "object" },
  },
} satisfies Meta<typeof PlaceholderPage>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    title: "Clienti",
    description: "Gestisci i tuoi clienti e i loro dati.",
  },
};

export const WithItems: Story = {
  args: {
    title: "Progetti",
    description: "Visualizza i tuoi progetti attivi.",
    items: ["Progetto Alpha", "Progetto Beta", "Progetto Gamma"],
  },
};

export const Empty: Story = {
  args: {
    title: "Archivio",
    description: "Nessun elemento nell'archivio.",
    items: [],
  },
};

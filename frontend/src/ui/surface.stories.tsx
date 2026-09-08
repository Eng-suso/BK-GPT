import type { Meta, StoryObj } from "@storybook/react";
import { Surface } from "./surface";
import { Button } from "./button";
import { Input } from "./input";
import { Textarea } from "./textarea";
import { Label } from "./label";

const meta = {
  title: "Design System/Satin materials",
  component: Surface,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof Surface>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Materials: Story = {
  render: () => (
    <div className="app-material min-h-screen space-y-6 p-8">
      <div className="grid gap-5 sm:grid-cols-2">
        <Surface className="space-y-4 p-5">
          <h2 className="font-semibold">Pannello operativo</h2>
          <Surface variant="inset" className="p-3 text-sm">Informazioni secondarie</Surface>
          <div className="flex flex-wrap gap-2">
            <Button>Salva</Button><Button variant="outline">Annulla</Button>
            <Button variant="destructive">Elimina</Button>
          </div>
        </Surface>
        <Surface variant="floating" className="space-y-3 p-5">
          <h2 className="font-semibold">Campi e finestre</h2>
          <Label htmlFor="material-name">Nome progetto</Label>
          <Input id="material-name" placeholder="Nuovo progetto…" />
          <Label htmlFor="material-description">Descrizione</Label>
          <Textarea id="material-description" placeholder="Descrivi il processo…" />
        </Surface>
      </div>
      <Surface variant="framed" className="mx-2 space-y-6 p-6">
        <p>Superficie con doppia cornice, usata dal composer.</p>
        <div className="flex justify-end"><Button>Invia</Button></div>
      </Surface>
    </div>
  ),
};

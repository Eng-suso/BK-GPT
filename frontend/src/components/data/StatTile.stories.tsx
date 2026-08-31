import type { Meta, StoryObj } from "@storybook/react";

import { StatTile } from "./StatTile";
import { Meter } from "./Meter";

const meta: Meta<typeof StatTile> = {
  title: "Data/StatTile",
  component: StatTile,
};
export default meta;

type Story = StoryObj<typeof StatTile>;

export const Single: Story = {
  args: {
    label: "Attraversamento medio",
    value: "1g 3h",
    hint: "di cui 96% in attesa",
  },
};

export const Grid: Story = {
  render: () => (
    <div className="grid w-[360px] grid-cols-2 gap-2">
      <StatTile label="Casi completati" value="100" />
      <StatTile label="Attraversamento medio" value="1g 3h" hint="di cui 96% in attesa" />
      <StatTile label="Attesa media" value="1g 0h" />
      <StatTile label="Lavoro medio" value="7h 40min" />
      <StatTile label="Costo medio / caso" value="€136" hint="Totale €13.600" />
      <StatTile label="Risorsa più carica" value="100%" hint="Operatore" tone="danger" />
    </div>
  ),
};

export const WithMeter: Story = {
  render: () => (
    <div className="grid w-[320px] gap-3">
      <Meter value={51} tone="ok" />
      <Meter value={88} tone="warning" />
      <Meter value={97} tone="danger" />
    </div>
  ),
};

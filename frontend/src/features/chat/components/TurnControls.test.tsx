import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import { AutonomySelector, PostureSelector, ReasoningSelector } from "./TurnControls";

describe("PostureSelector", () => {
  it("offre solo le posture della sua chat, piu' Auto", async () => {
    render(
      <PostureSelector scopeType="process" value="auto" detected={null} onChange={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /postura/i }));

    const options = screen.getAllByRole("menuitemradio").map((item) => item.textContent ?? "");
    expect(options.map((text) => text.split(/(?=[A-Z][a-z])/)[0])).toEqual([
      "Auto",
      "Discover",
      "Improve",
      "Validate",
    ]);
    expect(screen.queryByText("Desk")).not.toBeInTheDocument();
  });

  it("in Auto mostra la postura che DeliR ha usato davvero", () => {
    render(
      <PostureSelector scopeType="process" value="auto" detected="improve" onChange={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /postura/i })).toHaveTextContent("Improve · auto");
  });

  it("una postura scelta dal consulente si mostra senza 'auto'", () => {
    render(
      <PostureSelector scopeType="canvas" value="review" detected="map" onChange={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /postura/i })).toHaveTextContent(/^Review$/);
  });
});

describe("AutonomySelector e ReasoningSelector", () => {
  it("l'autonomia cambia con un clic e dice cosa comporta", async () => {
    const onChange = vi.fn();
    render(<AutonomySelector value="auto" onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /autonomia/i }));
    expect(screen.getByText(/ogni scrittura diventa una proposta/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitemradio", { name: /chiedi approvazione/i }));
    expect(onChange).toHaveBeenCalledWith("ask");
  });

  it("il ragionamento e' un controllo a parte con lo stato a vista", () => {
    render(<ReasoningSelector value="high" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /ragionamento/i })).toHaveTextContent("Ragionamento: Profondo");
  });
});

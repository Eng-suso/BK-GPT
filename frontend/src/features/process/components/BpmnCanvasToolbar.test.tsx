import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "@/lib/i18n";
import { BpmnCanvasToolbar } from "./BpmnCanvasToolbar";

function renderToolbar(overrides: Partial<Parameters<typeof BpmnCanvasToolbar>[0]> = {}) {
  const onSave = vi.fn();
  render(
    <BpmnCanvasToolbar
      saveTone="ok"
      saveLabel="Salvato"
      isReady
      isSaving={false}
      hasUnsavedChanges={false}
      isHistoryOpen={false}
      versionCount={0}
      fileInputRef={createRef<HTMLInputElement>()}
      canvasChat={{}}
      properties={{}}
      onSave={onSave}
      onZoomIn={vi.fn()}
      onZoomOut={vi.fn()}
      onZoomFit={vi.fn()}
      onZoomReadable={vi.fn()}
      onImportClick={vi.fn()}
      onImportFile={vi.fn()}
      onExport={vi.fn()}
      onToggleHistory={vi.fn()}
      {...overrides}
    />,
  );
  return { onSave };
}

describe("BpmnCanvasToolbar", () => {
  it("disables Save until there are unsaved changes", () => {
    renderToolbar({ hasUnsavedChanges: false });
    expect(screen.getByRole("button", { name: /salva/i })).toBeDisabled();
  });

  it("enables Save and calls back on click when there are unsaved changes", async () => {
    const { onSave } = renderToolbar({ hasUnsavedChanges: true });
    const button = screen.getByRole("button", { name: /^salva$/i });
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(onSave).toHaveBeenCalledOnce();
  });

  it("exposes the contextual inspector action with its accessible name", async () => {
    const onToggle = vi.fn();
    renderToolbar({ properties: { isOpen: false, onToggle } });
    const inspector = screen.getByRole("button", { name: "Proprietà" });
    expect(inspector).toHaveAttribute("aria-pressed", "false");
    inspector.focus();
    await userEvent.keyboard("{Enter}");
    expect(onToggle).toHaveBeenCalledOnce();
  });
});

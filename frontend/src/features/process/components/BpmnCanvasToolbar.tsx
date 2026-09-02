import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import {
  Download,
  History,
  Maximize2,
  Minus,
  MoreHorizontal,
  PanelLeft,
  PanelRight,
  Plus,
  Save,
  Upload,
} from "lucide-react";

import { Button } from "@/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import { StatusIndicator, type StatusTone } from "@/components/status";

type PanelToggle = {
  isOpen?: boolean;
  onToggle?: () => void;
};

type BpmnCanvasToolbarProps = {
  saveTone: StatusTone;
  saveLabel: string;
  isReady: boolean;
  isSaving: boolean;
  hasUnsavedChanges: boolean;
  isHistoryOpen: boolean;
  versionCount: number;
  fileInputRef: RefObject<HTMLInputElement | null>;
  canvasChat: PanelToggle;
  properties: PanelToggle;
  onSave: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomFit: () => void;
  onImportClick: () => void;
  onImportFile: (file: File | undefined) => void;
  onExport: () => void;
  onToggleHistory: () => void;
};

export function BpmnCanvasToolbar({
  saveTone,
  saveLabel,
  isReady,
  isSaving,
  hasUnsavedChanges,
  isHistoryOpen,
  versionCount,
  fileInputRef,
  canvasChat,
  properties,
  onSave,
  onZoomIn,
  onZoomOut,
  onZoomFit,
  onImportClick,
  onImportFile,
  onExport,
  onToggleHistory,
}: BpmnCanvasToolbarProps) {
  const { t } = useTranslation("process");

  return (
    <header className="process-bpmn-toolbar">
      <div className="flex min-w-0 shrink-0 items-center gap-3">
        <h3>Canvas processo</h3>
        {(canvasChat.onToggle || properties.onToggle) && (
          <div className="flex items-center gap-1 border-l border-border pl-3">
            {canvasChat.onToggle && (
              <Button
                type="button"
                variant={canvasChat.isOpen ? "secondary" : "ghost"}
                size="icon-sm"
                onClick={canvasChat.onToggle}
                aria-pressed={canvasChat.isOpen}
                title={t("actions.toggleChat")}
                aria-label={t("actions.toggleChat")}
              >
                <PanelLeft className="size-4" />
              </Button>
            )}
            {properties.onToggle && (
              <Button
                type="button"
                variant={properties.isOpen ? "secondary" : "ghost"}
                size="icon-sm"
                onClick={properties.onToggle}
                aria-pressed={properties.isOpen}
                title={t("actions.toggleProperties")}
                aria-label={t("actions.toggleProperties")}
              >
                <PanelRight className="size-4" />
              </Button>
            )}
          </div>
        )}
      </div>

      <div className="process-bpmn-toolbar-actions">
        <StatusIndicator tone={saveTone} label={saveLabel} className="mr-1" />

        <div className="bpmn-zoom-group" aria-label="Controlli zoom">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onZoomFit}
            title="Centra e adatta diagramma"
          >
            <Maximize2 />
            Centra
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            onClick={onZoomIn}
            title="Ingrandisci"
            aria-label="Ingrandisci"
          >
            <Plus />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            onClick={onZoomOut}
            title="Riduci"
            aria-label="Riduci"
          >
            <Minus />
          </Button>
        </div>

        <input
          ref={fileInputRef}
          className="process-bpmn-file-input"
          type="file"
          accept=".bpmn,.xml,.bpm"
          onChange={(event) => onImportFile(event.target.files?.[0])}
        />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant={isHistoryOpen ? "secondary" : "outline"}
              size="icon-sm"
              aria-label="Importa, esporta, cronologia"
              title="Importa, esporta, cronologia"
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem disabled={!isReady} onClick={onImportClick}>
              <Upload />
              Importa BPMN
            </DropdownMenuItem>
            <DropdownMenuItem disabled={!isReady} onClick={onExport}>
              <Download />
              Esporta BPMN
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onToggleHistory}>
              <History />
              {isHistoryOpen ? "Nascondi cronologia" : "Cronologia versioni"}
              {versionCount > 0 ? ` (${versionCount})` : ""}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Button
          type="button"
          size="sm"
          disabled={!isReady || isSaving || !hasUnsavedChanges}
          onClick={onSave}
          title="Salva processo (Ctrl+S)"
        >
          <Save />
          {isSaving ? "Salvo…" : "Salva"}
        </Button>
      </div>
    </header>
  );
}

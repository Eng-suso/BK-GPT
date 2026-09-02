import { X } from "lucide-react";

import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Textarea } from "@/ui/textarea";
import type { SelectedBpmnElement } from "../bpmn/types";

type BpmnNodeInspectorProps = {
  element: SelectedBpmnElement;
  onNameChange: (name: string) => void;
  onDocChange: (doc: string) => void;
  onClose: () => void;
};

export function BpmnNodeInspector({
  element,
  onNameChange,
  onDocChange,
  onClose,
}: BpmnNodeInspectorProps) {
  return (
    <aside
      className="absolute right-[18px] bottom-[18px] z-50 w-[290px] rounded-[9px] border border-border bg-card p-3 shadow-lg"
      aria-label="Ispettore nodo selezionato"
    >
      <div className="mb-2.5 flex items-start justify-between gap-2 border-b border-border pb-2">
        <div className="min-w-0">
          <Badge
            variant="outline"
            className="mb-1 text-[10px] tracking-wide uppercase"
          >
            {element.type}
          </Badge>
          <strong className="block max-w-[210px] truncate text-[13px] text-foreground">
            {element.name || element.id}
          </strong>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          onClick={onClose}
          title="Chiudi ispettore"
          aria-label="Chiudi ispettore"
        >
          <X />
        </Button>
      </div>
      <div className="grid gap-2.5">
        <label className="grid gap-1.5">
          <span className="text-[11px] font-semibold text-muted-foreground">
            Etichetta / Nome
          </span>
          <Input
            type="text"
            className="h-8 text-xs"
            value={element.name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="es. Raccolta dati..."
          />
        </label>
        <label className="grid gap-1.5">
          <span className="text-[11px] font-semibold text-muted-foreground">
            Note / Documentazione
          </span>
          <Textarea
            rows={2}
            className="min-h-0 text-xs"
            value={element.documentation}
            onChange={(e) => onDocChange(e.target.value)}
            placeholder="Aggiungi dettagli o regole per questo nodo..."
          />
        </label>
      </div>
    </aside>
  );
}

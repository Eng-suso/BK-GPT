import { Button } from "@/ui/button";
import type { BpmnVersion } from "@/contracts/workspace";
import { formatVersionDate } from "../bpmn/xml";

type BpmnVersionHistoryProps = {
  versions: BpmnVersion[];
  restoringVersionId: number | null;
  isReady: boolean;
  hasUnsavedChanges: boolean;
  onRestore: (versionId: number) => void;
};

export function BpmnVersionHistory({
  versions,
  restoringVersionId,
  isReady,
  hasUnsavedChanges,
  onRestore,
}: BpmnVersionHistoryProps) {
  return (
    <aside className="process-bpmn-history" aria-label="Cronologia BPMN">
      <div className="border-b border-border p-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          Versioni
        </p>
        <strong className="mt-0.5 block text-[13px] font-semibold text-foreground">
          Cronologia
        </strong>
      </div>
      {versions.length === 0 ? (
        <p className="p-3 text-xs font-medium text-muted-foreground">
          Nessuna versione salvata.
        </p>
      ) : (
        <ul className="grid content-start gap-2 overflow-auto p-2.5">
          {versions.map((version) => (
            <li
              key={version.id}
              className="grid gap-2 rounded-md border border-border bg-card p-2.5"
            >
              <div className="grid min-w-0 gap-0.5">
                <strong className="text-xs font-semibold text-foreground">
                  v{version.id}
                </strong>
                <span className="text-[11px] font-medium text-muted-foreground">
                  {formatVersionDate(version.createdAt)}
                </span>
                <small className="truncate text-[11px] font-medium text-muted-foreground">
                  {version.changeSummary}
                </small>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={
                  !isReady ||
                  restoringVersionId === version.id ||
                  hasUnsavedChanges
                }
                onClick={() => onRestore(version.id)}
              >
                {restoringVersionId === version.id ? "..." : "Ripristina"}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

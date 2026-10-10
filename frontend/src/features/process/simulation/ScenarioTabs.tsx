import React from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Copy, MoreHorizontal, Plus, Trash2, Undo2 } from "lucide-react";

import { ConfirmDialog } from "@/components/feedback";
import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/ui/dropdown-menu";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/ui/select";

import { MAX_ALTERNATIVES, scenarioDisplayName, workspaceScenarios, type WorkspaceScenario } from "./scenarioWorkspace";
import { useScenarioChanges } from "./useScenarioChanges";
import type { ScenarioLab } from "./useScenarioLab";

/**
 * SIM-14: sopra il pannello Scenario, quale scenario del workspace si modifica
 * (AS-IS | A | B …) e, per un'alternativa, le sue differenze dall'AS-IS.
 */
export function ScenarioTabs({ lab }: { lab: ScenarioLab }): React.JSX.Element | null {
  const { t } = useTranslation("process");
  const { workspace, selectedScenario, selectScenario, baselineDraft, template, isSaving, workspaceError } = lab;
  const [creating, setCreating] = React.useState<WorkspaceScenario | "asIs" | null>(null);
  const [deleting, setDeleting] = React.useState<WorkspaceScenario | null>(null);
  const changes = useScenarioChanges(baselineDraft, template);
  const scenarios = workspaceScenarios(workspace);
  if (!workspace?.baseline || !selectedScenario) {
    return workspaceError ? <p role="alert" className="sim-scenario-error">{workspaceError}</p> : null;
  }
  const full = workspace.alternatives.length >= MAX_ALTERNATIVES;
  const list = selectedScenario.kind === "alternative" ? changes.read(selectedScenario) : [];
  const conflicts = list.filter((change) => change.conflict).length;

  return (
    <section className="sim-scenario-tabs ui-surface ui-surface-inset" aria-label={t("simulation.scenarios.tabsLabel")} data-sim-scenario-tabs>
      <div className="sim-scenario-tabs-row">
        <div role="group" aria-label={t("simulation.scenarios.tabsLabel")} className="sim-scenario-tablist">
          {scenarios.map((scenario) => (
            <Button
              key={scenario.id}
              size="sm"
              variant={scenario.id === selectedScenario.id ? "secondary" : "ghost"}
              aria-pressed={scenario.id === selectedScenario.id}
              onClick={() => selectScenario(scenario.kind === "baseline" ? null : scenario.id)}
              title={scenarioDisplayName(scenario)}
            >
              <span className="sim-scenario-label">{scenario.label}</span>
              {scenario.kind === "alternative" && <span className="sim-scenario-name">{scenario.name}</span>}
            </Button>
          ))}
        </div>
        <Button size="sm" variant="outline" disabled={full} title={full ? t("simulation.scenarios.full", { count: MAX_ALTERNATIVES }) : undefined} onClick={() => setCreating(selectedScenario.kind === "alternative" ? selectedScenario : "asIs")}>
          <Plus aria-hidden className="size-4" />
          {t("simulation.scenarios.new")}
        </Button>
      </div>

      <div className="sim-scenario-status">
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {isSaving ? t("simulation.scenarios.saving") : t("simulation.scenarios.saved")}
        </p>
        {selectedScenario.kind === "alternative" && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="icon" variant="ghost" aria-label={t("simulation.scenarios.actions", { name: scenarioDisplayName(selectedScenario) })}>
                <MoreHorizontal aria-hidden className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem disabled={full} onSelect={() => setCreating(selectedScenario)}>
                <Copy aria-hidden className="size-4" />
                {t("simulation.scenarios.duplicate")}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setDeleting(selectedScenario)}>
                <Trash2 aria-hidden className="size-4" />
                {t("simulation.scenarios.delete")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
      {workspaceError && <p role="alert" className="sim-scenario-error">{workspaceError}</p>}

      {selectedScenario.kind === "baseline" ? (
        <p className="text-xs text-muted-foreground">{t("simulation.scenarios.asIsHint")}</p>
      ) : list.length === 0 ? (
        <p className="text-xs text-muted-foreground" data-sim-scenario-changes>{t("simulation.scenarios.noChanges")}</p>
      ) : (
        <details className="sim-scenario-changes" open data-sim-scenario-changes>
          <summary>{t("simulation.scenarios.changes", { count: list.length })}</summary>
          {conflicts > 0 && (
            <p className="sim-scenario-conflicts" role="status">
              <AlertTriangle aria-hidden className="size-4 shrink-0" />
              {t("simulation.scenarios.conflicts", { count: conflicts })}
            </p>
          )}
          <ul>
            {list.map((change) => {
              const what = changes.text(change);
              return (
                <li key={change.index} className={change.conflict ? "is-conflict" : undefined}>
                  <span className="min-w-0">
                    {what}
                    {change.conflict && <small>{t("simulation.scenarios.conflictOp")}</small>}
                  </span>
                  <Button size="sm" variant="ghost" aria-label={t("simulation.scenarios.revertLabel", { what })} onClick={() => void lab.revertChange(selectedScenario, change.index)}>
                    <Undo2 aria-hidden className="size-3.5" />
                    {t("simulation.scenarios.revert")}
                  </Button>
                </li>
              );
            })}
          </ul>
        </details>
      )}

      <NewScenarioDialog
        lab={lab}
        from={creating}
        onClose={() => setCreating(null)}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={t("simulation.scenarios.deleteTitle", { name: deleting ? scenarioDisplayName(deleting) : "" })}
        description={t("simulation.scenarios.deleteBody")}
        confirmLabel={t("simulation.scenarios.deleteConfirm")}
        destructive
        onConfirm={async () => {
          if (deleting && !(await lab.deleteScenario(deleting))) throw new Error(t("simulation.scenarios.deleteTitle", { name: scenarioDisplayName(deleting) }));
        }}
      />
    </section>
  );
}

function NewScenarioDialog({ lab, from, onClose }: { lab: ScenarioLab; from: WorkspaceScenario | "asIs" | null; onClose: () => void }) {
  const { t } = useTranslation("process");
  const alternatives = lab.workspace?.alternatives ?? [];
  const [name, setName] = React.useState("");
  const [source, setSource] = React.useState("asIs");
  const [busy, setBusy] = React.useState(false);
  const [openedFor, setOpenedFor] = React.useState<typeof from>(null);
  // A ogni apertura: il nome proposto e il punto di partenza scelto da chi l'ha aperto.
  if (from !== openedFor) {
    setOpenedFor(from);
    if (from) {
      setSource(from === "asIs" ? "asIs" : String(from.id));
      setName(from === "asIs" ? "" : t("simulation.scenarios.copyName", { name: from.name }));
    }
  }
  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    const origin = alternatives.find((s) => String(s.id) === source);
    const created = await lab.createScenario(trimmed, origin);
    setBusy(false);
    if (created) onClose();
  };
  return (
    <Dialog open={from !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={create} className="grid gap-4">
          <DialogTitle>{t("simulation.scenarios.new")}</DialogTitle>
          <DialogDescription>{t("simulation.scenarios.newHint")}</DialogDescription>
          <div className="grid gap-1.5">
            <Label htmlFor="sim-new-scenario-name">{t("simulation.scenarios.name")}</Label>
            <Input id="sim-new-scenario-name" value={name} maxLength={120} placeholder={t("simulation.scenarios.namePlaceholder")} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="grid gap-1.5">
            <Label id="sim-new-scenario-source">{t("simulation.scenarios.startFrom")}</Label>
            <Select value={source} onValueChange={setSource}>
              <SelectTrigger className="w-full" aria-labelledby="sim-new-scenario-source">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="asIs">{t("simulation.scenarios.startFromAsIs")}</SelectItem>
                {alternatives.map((s) => <SelectItem key={s.id} value={String(s.id)}>{scenarioDisplayName(s)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {lab.workspaceError && <p role="alert" className="sim-scenario-error">{lab.workspaceError}</p>}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>{t("simulation.scenarios.cancel")}</Button>
            <Button type="submit" disabled={!name.trim() || busy}>{t("simulation.scenarios.create")}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

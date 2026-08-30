import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp } from "lucide-react";

import { Button } from "@/ui/button";
import { Input } from "@/ui/input";
import { Label } from "@/ui/label";
import { StatusIndicator, type StatusTone } from "@/components/status";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/ui/select";
import { cn } from "@/lib/utils";

import type { SimulationRun } from "./simulationTypes";
import { DEFAULT_SCENARIO, type ScenarioDraft } from "./simulationScenario";

const RUN_TONE: Record<SimulationRun["status"], StatusTone> = {
  pending: "pending",
  completed: "ok",
  failed: "danger",
};

type SimulationConfigBarProps = {
  isRunning: boolean;
  error: string | null;
  runs: SimulationRun[];
  activeRunId: number | null;
  onRun: (draft: ScenarioDraft) => void;
  onSelectRun: (run: SimulationRun) => void;
};

export function SimulationConfigBar({
  isRunning,
  error,
  runs,
  activeRunId,
  onRun,
  onSelectRun,
}: SimulationConfigBarProps): React.JSX.Element {
  const { t } = useTranslation("process");
  const fieldId = React.useId();
  const [draft, setDraft] = React.useState<ScenarioDraft>(DEFAULT_SCENARIO);
  const [expanded, setExpanded] = React.useState(true);

  const set = <K extends keyof ScenarioDraft>(key: K, value: ScenarioDraft[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }));
  const num = (raw: string) => (raw === "" ? 0 : Number(raw));

  return (
    <div className="min-w-0 overflow-hidden rounded-lg border border-border bg-card shadow-sm">
      <div className="flex flex-wrap items-end gap-x-3 gap-y-2 px-3 py-2.5">
        <NumField
          id={`${fieldId}-name`}
          label={t("simulation.fields.scenarioName")}
          className="min-w-[150px] flex-1"
        >
          <Input
            id={`${fieldId}-name`}
            className="h-8"
            value={draft.scenarioName}
            onChange={(e) => set("scenarioName", e.target.value)}
          />
        </NumField>

        {expanded && (
          <>
            <NumField id={`${fieldId}-cases`} label={t("simulation.fields.cases")}>
              <Input
                id={`${fieldId}-cases`}
                type="number"
                min={1}
                max={100000}
                className="h-8 w-[76px]"
                value={draft.totalCases}
                onChange={(e) => set("totalCases", num(e.target.value))}
              />
            </NumField>
            <NumField id={`${fieldId}-arrival`} label={t("simulation.fields.arrival")}>
              <Input
                id={`${fieldId}-arrival`}
                type="number"
                min={1}
                className="h-8 w-[76px]"
                value={draft.arrivalIntervalMinutes}
                onChange={(e) => set("arrivalIntervalMinutes", num(e.target.value))}
              />
            </NumField>
            <NumField id={`${fieldId}-dur`} label={t("simulation.fields.taskDuration")}>
              <Input
                id={`${fieldId}-dur`}
                type="number"
                min={1}
                className="h-8 w-[76px]"
                value={draft.taskDurationMinutes}
                onChange={(e) => set("taskDurationMinutes", num(e.target.value))}
              />
            </NumField>
            <NumField id={`${fieldId}-cost`} label={t("simulation.fields.costPerHour")}>
              <Input
                id={`${fieldId}-cost`}
                type="number"
                min={0}
                step={0.01}
                className="h-8 w-[76px]"
                value={draft.costPerHour}
                onChange={(e) => set("costPerHour", num(e.target.value))}
              />
            </NumField>
            <NumField id={`${fieldId}-res`} label={t("simulation.fields.resources")}>
              <Input
                id={`${fieldId}-res`}
                type="number"
                min={1}
                max={1000}
                className="h-8 w-[76px]"
                value={draft.resourceAmount}
                onChange={(e) => set("resourceAmount", num(e.target.value))}
              />
            </NumField>
            <NumField
              id={`${fieldId}-pool`}
              label={t("simulation.fields.resourcePool")}
              className="min-w-[120px]"
            >
              <Input
                id={`${fieldId}-pool`}
                className="h-8"
                value={draft.resourceName}
                onChange={(e) => set("resourceName", e.target.value)}
              />
            </NumField>
          </>
        )}

        <div className="flex items-end gap-2">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8 px-2 text-muted-foreground"
            onClick={() => setExpanded((v) => !v)}
            title={expanded ? t("simulation.config.collapse") : t("simulation.config.expand")}
          >
            {expanded ? (
              <ChevronUp className="size-4" />
            ) : (
              <ChevronDown className="size-4" />
            )}
          </Button>
          <Button
            type="button"
            size="sm"
            className="h-8"
            disabled={isRunning}
            onClick={() => onRun(draft)}
          >
            {isRunning ? t("simulation.running") : t("simulation.run")}
          </Button>
        </div>

        {runs.length > 0 && (
          <div className="ml-auto flex items-end gap-1.5">
            <span className="pb-1.5 text-[11px] font-semibold text-muted-foreground">
              {t("simulation.output.title")}
            </span>
            <Select
              value={activeRunId ? String(activeRunId) : undefined}
              onValueChange={(value) => {
                const run = runs.find((r) => r.id === Number(value));
                if (run) onSelectRun(run);
              }}
            >
              <SelectTrigger className="h-8 w-[220px]">
                <SelectValue placeholder={t("simulation.output.title")} />
              </SelectTrigger>
              <SelectContent>
                {runs.map((run) => (
                  <SelectItem key={run.id} value={String(run.id)}>
                    <span className="flex items-center gap-2">
                      <StatusIndicator
                        tone={RUN_TONE[run.status]}
                        label={run.scenario_name}
                      />
                      <span className="text-[11px] text-muted-foreground">
                        {formatDate(run.created_at)}
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      {error && (
        <p
          role="alert"
          className="border-t border-destructive/20 bg-destructive/5 px-3 py-1.5 text-xs font-medium text-destructive"
        >
          {error}
        </p>
      )}
    </div>
  );
}

function NumField({
  id,
  label,
  className,
  children,
}: {
  id: string;
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("grid gap-1", className)}>
      <Label
        htmlFor={id}
        className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
      >
        {label}
      </Label>
      {children}
    </div>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

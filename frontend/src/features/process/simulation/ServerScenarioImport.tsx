import { useTranslation } from "react-i18next";

import { InlineNotice } from "@/components/feedback";
import { Button } from "@/ui/button";

import { groupNotes, importSummary, type ProsimosImport } from "./prosimosServerImport";

const KNOWN_TOPICS = new Set(["merge_gateway", "unused_calendar", "instant_activity", "missing_branch", "rounded_probabilities", "probabilistic_calendars"]);

/** B1b: lo scenario che l'editor non rappresenta, letto dal server e pronto da simulare cosi' com'e'. */
export function ServerScenarioImport({ name, result, running, onRun }: {
  name: string;
  result: ProsimosImport;
  running: boolean;
  onRun: () => void;
}) {
  const { t } = useTranslation("process");
  const summary = importSummary(result);
  const groups = groupNotes(result.notes);
  const attention = groups.filter((group) => group.kind === "approximated");
  const info = groups.filter((group) => group.kind === "info");

  const renderGroup = (group: (typeof groups)[number]) => (
    <li key={group.topic}>
      <p>{t(`simulation.scenario.serverImport.topics.${KNOWN_TOPICS.has(group.topic) ? group.topic : "other"}`, { count: group.notes.length })}</p>
      <details className="mt-1">
        <summary className="cursor-pointer text-muted-foreground">{t("simulation.scenario.serverImport.details", { count: group.notes.length })}</summary>
        <ul className="mt-1 grid gap-1 text-muted-foreground">
          {group.notes.map((note, index) => <li key={`${note.element_id ?? ""}-${index}`}>{note.message}</li>)}
        </ul>
      </details>
    </li>
  );

  return (
    <section className="grid gap-3 rounded-lg border border-border bg-muted/30 p-4 text-sm" aria-label={t("simulation.scenario.serverImport.title")}>
      <div>
        <h3 className="font-semibold">{t("simulation.scenario.serverImport.title")}</h3>
        <p className="mt-1 text-muted-foreground">
          {t(attention.length > 0 ? "simulation.scenario.serverImport.descriptionAdjusted" : "simulation.scenario.serverImport.description", { name })}
        </p>
      </div>
      <p className="font-medium">{t("simulation.scenario.serverImport.summary", summary)}</p>
      {summary.fromSimod && <p className="text-muted-foreground">{t("simulation.scenario.serverImport.fromSimod")}</p>}
      {attention.length > 0 && (
        <InlineNotice tone="warning" title={t("simulation.scenario.serverImport.attention")}>
          <ul className="grid gap-2">{attention.map(renderGroup)}</ul>
        </InlineNotice>
      )}
      {info.length > 0 && (
        <div>
          <h4 className="font-medium">{t("simulation.scenario.serverImport.info")}</h4>
          <ul className="mt-1 grid gap-2">{info.map(renderGroup)}</ul>
        </div>
      )}
      <p className="text-muted-foreground">{t("simulation.scenario.serverImport.editorNote")}</p>
      <div>
        <Button type="button" onClick={onRun} disabled={running} aria-busy={running}>
          {running ? t("simulation.scenario.serverImport.running") : t("simulation.scenario.serverImport.runAsIs")}
        </Button>
      </div>
    </section>
  );
}

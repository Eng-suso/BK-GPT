import React from "react";
import { useTranslation } from "react-i18next";
import { Download } from "lucide-react";

import { Button } from "@/ui/button";

import { downloadRunLog, type RunLogFormat } from "./runLog";
import type { SimulationRun } from "./simulationTypes";

/**
 * SIM-06b: scarica il log simulato del run, in CSV o XES, per rileggerlo in un
 * altro strumento di process mining o reimportarlo nel wizard. Un run vecchio
 * senza log conservato lo dice, invece di non fare nulla.
 */
export function RunLogDownload({ run }: { run: SimulationRun }): React.JSX.Element {
  const { t } = useTranslation("process");
  const [busy, setBusy] = React.useState<RunLogFormat | null>(null);
  const [error, setError] = React.useState(false);

  const download = async (format: RunLogFormat) => {
    setBusy(format);
    setError(false);
    try {
      await downloadRunLog(run, format);
    } catch {
      setError(true);
    } finally {
      setBusy(null);
    }
  };

  return (
    <span className="flex flex-wrap items-center gap-2" data-run-log-download>
      {(["csv", "xes"] as const).map((format) => (
        <Button key={format} type="button" size="sm" variant="outline" disabled={busy !== null}
          aria-label={t("simulation.runLog.downloadAs", { format: format.toUpperCase() })}
          onClick={() => void download(format)}>
          <Download aria-hidden className="size-3.5" />
          {t("simulation.runLog.label", { format: format.toUpperCase() })}
        </Button>
      ))}
      {error && <span role="alert" className="basis-full text-xs font-medium text-destructive">{t("simulation.runLog.error")}</span>}
    </span>
  );
}

import React from "react";
import { useTranslation } from "react-i18next";

import type { ProsimosIdMapping } from "./prosimosJson";
import { prosimosReferenceFields } from "./prosimosReferences";
import type { ScenarioTemplate } from "./simulationTypes";

export function ProsimosReferenceMapping({ source, template, mapping, onChange }: {
  source: Record<string, unknown>;
  template: ScenarioTemplate;
  mapping: ProsimosIdMapping;
  onChange: (mapping: ProsimosIdMapping) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const fields = prosimosReferenceFields(source, template, mapping);
  const labels: Record<keyof ProsimosIdMapping, string> = {
    tasks: t("simulation.scenario.referenceTask"), gateways: t("simulation.scenario.referenceGateway"),
    flows: t("simulation.scenario.referenceFlow"), waits: t("simulation.scenario.referenceWait"),
  };
  return <div className="grid gap-3 rounded-lg border border-border p-3 text-sm">
    <p className="font-medium">{t("simulation.scenario.referenceMappingTitle")}</p>
    <p className="text-muted-foreground">{t("simulation.scenario.referenceMappingHint")}</p>
    {fields.map((field) => <label className="grid gap-1" key={`${field.kind}:${field.key}`}>
      <span>{labels[field.kind]} · <code className="break-all">{field.source}</code></span>
      <select className="min-h-10 w-full rounded-lg border border-border bg-background px-3" value={mapping[field.kind]?.[field.key] ?? ""}
        onChange={(event) => onChange({ ...mapping, [field.kind]: { ...mapping[field.kind], [field.key]: event.target.value } })}>
        <option value="">{t("simulation.scenario.referenceChoose")}</option>
        {field.options.map((option) => <option key={option.id} value={option.id}>{option.label} · {option.id}</option>)}
      </select>
    </label>)}
  </div>;
}

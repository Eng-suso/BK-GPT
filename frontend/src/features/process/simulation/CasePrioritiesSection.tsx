import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/ui/button";

import { ConditionGroups } from "./GatewayRulesEditor";
import { defaultRule, type BranchRuleDraft, type CaseAttributeDraft } from "./caseRules";

/**
 * SIM-12: chi passa prima quando piu' casi aspettano la stessa risorsa. La priorita' 1
 * e' servita per prima, poi la 2; i casi che non rispettano nessuna regola aspettano
 * in ordine di arrivo. Le condizioni sono quelle dei rami per regola.
 */
export function CasePrioritiesSection({
  priorities,
  attributes,
  onChange,
}: {
  priorities: BranchRuleDraft[];
  attributes: CaseAttributeDraft[];
  onChange: (next: BranchRuleDraft[]) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const noAttributes = attributes.length === 0;
  return (
    <div className="grid gap-3" data-sim-priorities>
      <p className="text-sm leading-relaxed text-muted-foreground">{t("simulation.config.prioritiesHint")}</p>
      {priorities.map((groups, index) => {
        const level = index + 1;
        return (
          <ConditionGroups
            key={index}
            id={`priority-${level}`}
            legend={t("simulation.config.priorityLevel", { level })}
            subject={t("simulation.config.priorityLevel", { level })}
            groups={groups}
            attributes={attributes}
            sentenceKey="simulation.config.priorityReads"
            onChange={(next) => onChange(priorities.map((g, i) => (i === index ? next : g)))}
            action={
              <Button type="button" size="sm" variant="ghost" className="h-7 gap-1 px-2 text-xs"
                aria-label={t("simulation.config.removePriority", { level })}
                onClick={() => onChange(priorities.filter((_, i) => i !== index))}>
                <X aria-hidden className="size-3.5" />
                {t("simulation.config.removePriorityShort")}
              </Button>
            }
          />
        );
      })}
      <Button type="button" size="sm" variant="outline" className="h-8 w-fit gap-1 px-2 text-xs"
        disabled={noAttributes}
        aria-describedby={noAttributes ? "sim-priorities-need-attribute" : undefined}
        onClick={() => onChange([...priorities, [[defaultRule(attributes)]]])}>
        <Plus aria-hidden className="size-3.5" />
        {t("simulation.config.addPriority")}
      </Button>
      {noAttributes && <p id="sim-priorities-need-attribute" className="text-xs text-muted-foreground">{t("simulation.config.prioritiesNeedAttribute")}</p>}
    </div>
  );
}

import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import {
  defaultRule,
  operatorsFor,
  ruleIssue,
  ruleSentence,
  type BranchRuleDraft,
  type CaseAttributeDraft,
  type GatewayRulesDraft,
  type RuleDraft,
  type RuleOperator,
} from "./caseRules";
import type { ScenarioTemplate } from "./simulationTypes";

type Gateway = ScenarioTemplate["gateways"][number];

const NATIVE_SELECT = "h-8 w-full min-w-0 ui-field rounded-xl px-2 text-sm";

/** Il modo della decisione: a percentuale (sul pannello) o per regola sugli attributi del caso. */
export function GatewayModeToggle({ gateway, rules, attributes, onChange }: {
  gateway: Gateway;
  rules: GatewayRulesDraft | undefined;
  attributes: CaseAttributeDraft[];
  onChange: (rules: GatewayRulesDraft | undefined) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const byRule = rules !== undefined;
  const noAttributes = attributes.length === 0;
  const hintId = `sim-gateway-mode-hint-${gateway.element_id}`;
  return (
    <div className="grid gap-1">
      <div role="group" aria-label={t("simulation.config.gatewayMode", { name: gateway.name })} className="inline-flex w-fit rounded-lg border border-border p-0.5">
        <Button type="button" size="sm" variant={byRule ? "ghost" : "secondary"} aria-pressed={!byRule} className="h-7 px-2.5 text-xs" onClick={() => onChange(undefined)}>
          {t("simulation.config.gatewayByPercent")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant={byRule ? "secondary" : "ghost"}
          aria-pressed={byRule}
          disabled={noAttributes && !byRule}
          aria-describedby={noAttributes ? hintId : undefined}
          className="h-7 px-2.5 text-xs"
          onClick={() => !byRule && onChange(Object.fromEntries(gateway.branches.map((b) => [b.flow_id, [[defaultRule(attributes)]]])))}
        >
          {t("simulation.config.gatewayByRule")}
        </Button>
      </div>
      {noAttributes && !byRule && <p id={hintId} className="text-xs text-muted-foreground">{t("simulation.config.gatewayRuleNeedsAttribute")}</p>}
    </div>
  );
}

/** Le regole di ogni ramo: gruppi in "oppure", condizioni di un gruppo in "e". */
export function GatewayRulesEditor({ gateway, rules, attributes, onChange }: {
  gateway: Gateway;
  rules: GatewayRulesDraft;
  attributes: CaseAttributeDraft[];
  onChange: (rules: GatewayRulesDraft) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const words = { and: t("simulation.activityInspector.and"), or: t("simulation.config.ruleOr") };
  const setBranch = (flowId: string, groups: BranchRuleDraft) => onChange({ ...rules, [flowId]: groups });

  return (
    <div className="grid gap-3">
      <p className="text-xs leading-relaxed text-muted-foreground">{t("simulation.config.gatewayRuleHint")}</p>
      {gateway.branches.map((branch) => {
        const groups = rules[branch.flow_id] ?? [];
        const issue = ruleIssue(groups, attributes);
        const issueId = `sim-rule-issue-${gateway.element_id}-${branch.flow_id}`;
        const label = branch.target_name || branch.flow_name || branch.flow_id;
        return (
          <fieldset key={branch.flow_id} className="min-w-0 rounded-lg border border-border bg-card p-2.5" aria-describedby={issue ? issueId : undefined}>
            <legend className="px-1 text-xs font-medium text-foreground">{t("simulation.config.branchTo", { name: label })}</legend>
            <div className="grid gap-2">
              {groups.map((group, groupIndex) => (
                <div key={groupIndex} className="grid gap-1.5">
                  {groupIndex > 0 && <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{words.or}</p>}
                  {group.map((rule, ruleIndex) => (
                    <RuleRow
                      key={ruleIndex}
                      rule={rule}
                      attributes={attributes}
                      prefix={ruleIndex === 0 ? t("simulation.config.ruleIf") : words.and}
                      branchLabel={label}
                      describedBy={issue ? issueId : undefined}
                      onChange={(next) => setBranch(branch.flow_id, groups.map((g, gi) => gi === groupIndex ? g.map((r, ri) => (ri === ruleIndex ? next : r)) : g))}
                      onRemove={() => setBranch(branch.flow_id, groups
                        .map((g, gi) => (gi === groupIndex ? g.filter((_, ri) => ri !== ruleIndex) : g))
                        .filter((g) => g.length > 0))}
                    />
                  ))}
                  <Button type="button" size="sm" variant="ghost" className="h-7 w-fit gap-1 px-2 text-xs"
                    onClick={() => setBranch(branch.flow_id, groups.map((g, gi) => (gi === groupIndex ? [...g, defaultRule(attributes)] : g)))}>
                    <Plus aria-hidden className="size-3.5" />
                    {t("simulation.config.addCondition")}
                  </Button>
                </div>
              ))}
              <Button type="button" size="sm" variant="outline" className="h-7 w-fit gap-1 px-2 text-xs"
                onClick={() => setBranch(branch.flow_id, [...groups, [defaultRule(attributes)]])}>
                <Plus aria-hidden className="size-3.5" />
                {t(groups.length ? "simulation.config.addAlternative" : "simulation.config.addRule")}
              </Button>
              {!issue && <p className="text-xs text-muted-foreground">{t("simulation.config.ruleReads", { rule: ruleSentence(groups, attributes, words) })}</p>}
              {issue && <p id={issueId} role="alert" className="text-xs font-medium text-destructive">{t(`simulation.config.ruleIssue.${issue}`)}</p>}
            </div>
          </fieldset>
        );
      })}
    </div>
  );
}

function RuleRow({ rule, attributes, prefix, branchLabel, describedBy, onChange, onRemove }: {
  rule: RuleDraft;
  attributes: CaseAttributeDraft[];
  prefix: string;
  branchLabel: string;
  describedBy?: string;
  onChange: (rule: RuleDraft) => void;
  onRemove: () => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const attribute = attributes.find((a) => a.id === rule.attributeId);
  const operators = operatorsFor(attribute);
  const name = attribute?.name || "?";
  return (
    <div className="grid grid-cols-[auto_minmax(0,1.3fr)_minmax(64px,0.7fr)_minmax(0,1fr)_auto] items-center gap-1.5">
      <span className="w-6 text-[11px] text-muted-foreground">{prefix}</span>
      <select
        className={NATIVE_SELECT}
        aria-label={t("simulation.config.ruleAttribute", { branch: branchLabel })}
        aria-describedby={describedBy}
        value={attribute ? rule.attributeId : ""}
        onChange={(e) => {
          const next = attributes.find((a) => a.id === e.target.value);
          const start = defaultRule(next ? [next] : []);
          onChange({ ...start, operator: operatorsFor(next).includes(rule.operator) ? rule.operator : start.operator });
        }}
      >
        {!attribute && <option value="">{t("simulation.config.ruleChooseAttribute")}</option>}
        {attributes.map((a) => <option key={a.id} value={a.id}>{a.name || t("simulation.config.unnamedAttribute")}</option>)}
      </select>
      <select
        className={NATIVE_SELECT}
        aria-label={t("simulation.config.ruleOperator", { attribute: name })}
        value={rule.operator}
        onChange={(e) => onChange({ ...rule, operator: e.target.value as RuleOperator })}
      >
        {operators.map((op) => <option key={op} value={op}>{t(`simulation.config.operator.${OPERATOR_KEY[op]}`)}</option>)}
      </select>
      {attribute?.kind === "category" ? (
        <select
          className={NATIVE_SELECT}
          aria-label={t("simulation.config.ruleValue", { attribute: name })}
          aria-describedby={describedBy}
          value={rule.value}
          onChange={(e) => onChange({ ...rule, value: e.target.value })}
        >
          {!attribute.categories.some((c) => c.value === rule.value) && <option value={rule.value}>{rule.value || "—"}</option>}
          {attribute.categories.filter((c) => c.value.trim()).map((c) => <option key={c.value} value={c.value}>{c.value}</option>)}
        </select>
      ) : (
        <Input
          className="h-8"
          inputMode="decimal"
          aria-label={t("simulation.config.ruleValue", { attribute: name })}
          aria-describedby={describedBy}
          value={rule.value}
          onChange={(e) => onChange({ ...rule, value: e.target.value })}
        />
      )}
      <Button type="button" size="icon" variant="ghost" aria-label={t("simulation.config.removeCondition", { attribute: name })} onClick={onRemove}>
        <X aria-hidden className="size-4" />
      </Button>
    </div>
  );
}

const OPERATOR_KEY: Record<RuleOperator, string> = { ">": "gt", ">=": "gte", "<": "lt", "<=": "lte", "=": "eq", "!=": "neq" };

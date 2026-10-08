import React from "react";
import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";

import { Button } from "@/ui/button";
import { Input } from "@/ui/input";

import { attributeIssue, categorySum, newAttributeId, type CaseAttributeDraft } from "./caseRules";

type Category = Extract<CaseAttributeDraft, { kind: "category" }>;

/**
 * Gli attributi che ogni caso riceve all'arrivo: categorie con la loro quota
 * (premium 30%, standard 70%) o un numero fra un minimo e un massimo. Servono
 * alle decisioni per regola, e finiscono nel log simulato.
 */
export function CaseAttributesSection({ attributes, usedBy, onChange }: {
  attributes: CaseAttributeDraft[];
  /** Quante decisioni usano ciascun attributo: non si toglie un attributo in uso. */
  usedBy: Record<string, number>;
  onChange: (next: CaseAttributeDraft[]) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const update = (id: string, next: CaseAttributeDraft) => onChange(attributes.map((a) => (a.id === id ? next : a)));

  return (
    <div className="grid gap-3">
      <p className="text-sm leading-relaxed text-muted-foreground">{t("simulation.config.attributesHint")}</p>
      <ul className="grid gap-3">
        {attributes.map((attribute) => {
          const issue = attributeIssue(attribute, attributes);
          const issueId = `sim-attribute-issue-${attribute.id}`;
          const inUse = usedBy[attribute.id] ?? 0;
          return (
            <li key={attribute.id} data-attribute-id={attribute.id} className="min-w-0 rounded-lg border border-border bg-card p-3">
              <div className="mb-3 flex items-end gap-2">
                <label className="grid min-w-0 flex-1 gap-1">
                  <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.attributeName")}</span>
                  <Input
                    className="h-8"
                    value={attribute.name}
                    maxLength={64}
                    aria-invalid={issue === "name" || issue === "duplicateName" ? true : undefined}
                    aria-describedby={issue ? issueId : undefined}
                    onChange={(e) => update(attribute.id, { ...attribute, name: e.target.value })}
                  />
                </label>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  disabled={inUse > 0}
                  aria-label={t("simulation.config.removeAttribute", { name: attribute.name })}
                  onClick={() => onChange(attributes.filter((a) => a.id !== attribute.id))}
                >
                  <X aria-hidden className="size-4" />
                </Button>
              </div>
              {inUse > 0 && <p className="-mt-2 mb-3 text-xs text-muted-foreground">{t("simulation.config.attributeInUse", { count: inUse })}</p>}
              <div role="group" aria-label={t("simulation.config.attributeKind")} className="mb-3 inline-flex rounded-lg border border-border p-0.5">
                {(["category", "number"] as const).map((kind) => (
                  <Button
                    key={kind}
                    type="button"
                    size="sm"
                    variant={attribute.kind === kind ? "secondary" : "ghost"}
                    aria-pressed={attribute.kind === kind}
                    className="h-7 px-2.5 text-xs"
                    onClick={() => attribute.kind !== kind && update(attribute.id, kind === "number"
                      ? { id: attribute.id, name: attribute.name, kind, minimum: 0, maximum: 1000 }
                      : { id: attribute.id, name: attribute.name, kind, categories: [{ value: "", percent: 100 }] })}
                  >
                    {t(`simulation.config.attributeKindName.${kind}`)}
                  </Button>
                ))}
              </div>
              {attribute.kind === "category"
                ? <CategoryFields attribute={attribute} invalid={issue} describedBy={issue ? issueId : undefined} onChange={(next) => update(attribute.id, next)} />
                : (
                  <div className="grid grid-cols-2 gap-2">
                    {(["minimum", "maximum"] as const).map((bound) => (
                      <label key={bound} className="grid gap-1">
                        <span className="text-xs font-medium text-muted-foreground">{t(`simulation.config.attribute.${bound}`)}</span>
                        <Input
                          className="h-8"
                          type="number"
                          value={Number.isFinite(attribute[bound]) ? attribute[bound] : ""}
                          aria-invalid={issue === "bounds" ? true : undefined}
                          aria-describedby={issue ? issueId : undefined}
                          onChange={(e) => update(attribute.id, { ...attribute, [bound]: e.target.value === "" ? Number.NaN : Number(e.target.value) })}
                        />
                      </label>
                    ))}
                    <p className="col-span-2 text-xs text-muted-foreground">{t("simulation.config.attributeNumberHint")}</p>
                  </div>
                )}
              {issue && (
                <p id={issueId} role="alert" className="mt-2 text-xs font-medium text-destructive">
                  {t(`simulation.config.attributeIssue.${issue}`)}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      <div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 gap-1 px-2 text-xs"
          onClick={() => onChange([
            ...attributes,
            {
              id: newAttributeId(attributes),
              name: t("simulation.config.newAttributeName", { n: attributes.length + 1 }),
              kind: "category",
              categories: [{ value: "", percent: 50 }, { value: "", percent: 50 }],
            },
          ])}
        >
          <Plus aria-hidden className="size-3.5" />
          {t("simulation.config.addAttribute")}
        </Button>
      </div>
    </div>
  );
}

function CategoryFields({ attribute, invalid, describedBy, onChange }: {
  attribute: Category;
  invalid: string | null;
  describedBy?: string;
  onChange: (next: Category) => void;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const sum = categorySum(attribute);
  const patch = (index: number, next: Partial<Category["categories"][number]>) =>
    onChange({ ...attribute, categories: attribute.categories.map((c, i) => (i === index ? { ...c, ...next } : c)) });
  return (
    <div className="grid gap-2">
      <ul className="grid gap-1.5">
        {attribute.categories.map((category, index) => (
          <li key={index} className="grid grid-cols-[minmax(0,1fr)_84px_auto] items-end gap-2">
            <label className="grid min-w-0 gap-1">
              <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.categoryValue", { n: index + 1 })}</span>
              <Input
                className="h-8"
                value={category.value}
                maxLength={64}
                aria-invalid={invalid === "categoryValue" && !category.value.trim() ? true : undefined}
                aria-describedby={describedBy}
                onChange={(e) => patch(index, { value: e.target.value })}
              />
            </label>
            <label className="grid gap-1">
              <span className="text-xs font-medium text-muted-foreground">{t("simulation.config.categoryShare")}</span>
              <span className="relative">
                <Input
                  className="h-8 pr-6"
                  type="number"
                  min={0}
                  max={100}
                  value={Number.isFinite(category.percent) ? category.percent : ""}
                  aria-invalid={invalid === "categorySum" ? true : undefined}
                  aria-describedby={describedBy}
                  onChange={(e) => patch(index, { percent: e.target.value === "" ? Number.NaN : Number(e.target.value) })}
                />
                <span aria-hidden className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">%</span>
              </span>
            </label>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              disabled={attribute.categories.length === 1}
              aria-label={t("simulation.config.removeCategory", { value: category.value || index + 1 })}
              onClick={() => onChange({ ...attribute, categories: attribute.categories.filter((_, i) => i !== index) })}
            >
              <X aria-hidden className="size-4" />
            </Button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 gap-1 px-2 text-xs"
          onClick={() => onChange({ ...attribute, categories: [...attribute.categories, { value: "", percent: 0 }] })}
        >
          <Plus aria-hidden className="size-3.5" />
          {t("simulation.config.addCategory")}
        </Button>
        <span className="text-xs tabular-nums text-muted-foreground">{t("simulation.config.categoryTotal", { value: Math.round(sum * 10) / 10 })}</span>
      </div>
    </div>
  );
}

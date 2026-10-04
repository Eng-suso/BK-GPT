import React from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, CircleAlert, Loader2 } from "lucide-react";

import type { ClaimRelation, ClaimRelationSide, DivergenceType, ProjectSource } from "@/contracts/workspace";
import { useSourceRelationsQuery } from "../api";

/** Le divergenze che chiedono una scelta: le altre sono differenze da leggere. */
const SERIOUS: ReadonlySet<DivergenceType> = new Set(["incompatible", "tension_to_explore"]);

/**
 * Il confronto di una fonte con gli altri file del processo (P1.13).
 *
 * Un conflitto non si risolve in silenzio: ogni divergenza mostra le due
 * affermazioni una accanto all'altra, ognuna con il suo file, la sua ancora e
 * la sua citazione. Sotto, le affermazioni che altri file confermano.
 */
export function SourceRelationsSection({ source }: { source: ProjectSource }): React.JSX.Element | null {
  const { t } = useTranslation("projects");
  const relations = useSourceRelationsQuery(source.id, source.reconcileStatus);

  if (source.claimsStatus !== "done" || source.reconcileStatus === null) return null;

  let body: React.ReactNode;
  if (source.reconcileStatus === "pending") {
    body = (
      <p className="flex items-center gap-1.5 text-body-sm text-muted-foreground" role="status">
        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        {t("detail.sources.relations.pending")}
      </p>
    );
  } else if (relations.isError) {
    body = (
      <p className="text-body-sm text-destructive" role="alert">
        {t("detail.sources.relations.loadFailed")}
      </p>
    );
  } else if (relations.isLoading) {
    body = <p className="text-body-sm text-muted-foreground">{t("detail.sources.relations.loading")}</p>;
  } else {
    const divergences = (relations.data ?? []).filter((relation) => relation.kind === "divergence");
    const corroborations = (relations.data ?? []).filter((relation) => relation.kind === "corroboration");
    body = (
      <>
        {source.reconcileStatus === "failed" ? (
          <p className="text-body-sm text-[var(--color-status-warning)]" role="alert">
            {t("detail.sources.relations.failed")}
          </p>
        ) : null}
        {divergences.length === 0 && corroborations.length === 0 && source.reconcileStatus === "done" ? (
          <p className="text-body-sm text-muted-foreground">{t("detail.sources.relations.none")}</p>
        ) : null}
        {divergences.length > 0 ? (
          <div className="flex flex-col gap-2">
            <h4 className="text-body-sm font-medium text-foreground">
              {t("detail.sources.relations.divergences", { count: divergences.length })}
            </h4>
            <ul className="flex flex-col gap-3">
              {divergences.map((relation) => (
                <DivergenceItem key={relation.id} relation={relation} />
              ))}
            </ul>
          </div>
        ) : null}
        {corroborations.length > 0 ? (
          <div className="flex flex-col gap-1.5">
            <h4 className="text-body-sm font-medium text-foreground">
              {t("detail.sources.relations.corroborations", { count: corroborations.length })}
            </h4>
            <ul className="flex flex-col gap-1.5">
              {corroborations.map((relation) => (
                <li key={relation.id} className="flex flex-col gap-0.5 border-l-2 border-border pl-3">
                  <p className="text-body-sm leading-relaxed text-foreground">{relation.claim.statement}</p>
                  <p className="inline-flex items-center gap-1 text-micro text-[var(--color-status-success)]">
                    <CheckCircle2 className="size-3" aria-hidden="true" />
                    {t("detail.sources.relations.confirmedBy", { source: relation.other.sourceName })}
                    <span className="font-mono text-muted-foreground">{relation.other.anchorRef}</span>
                  </p>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </>
    );
  }

  return (
    <section className="flex shrink-0 flex-col gap-2" aria-labelledby={`relations-${source.id}`}>
      <h3
        id={`relations-${source.id}`}
        className="text-micro font-medium tracking-wide text-muted-foreground uppercase"
      >
        {t("detail.sources.relations.heading")}
      </h3>
      {body}
    </section>
  );
}

function DivergenceItem({ relation }: { relation: ClaimRelation }): React.JSX.Element {
  const { t } = useTranslation("projects");
  const type = relation.divergenceType ?? "tension_to_explore";
  const serious = SERIOUS.has(type);
  return (
    <li
      className={`flex flex-col gap-2 rounded-md border p-3 ${
        serious ? "border-[var(--color-status-warning)]" : "border-border"
      }`}
    >
      <span
        className={`inline-flex w-fit items-center gap-1 text-micro font-medium ${
          serious ? "text-[var(--color-status-warning)]" : "text-muted-foreground"
        }`}
      >
        {serious ? <CircleAlert className="size-3" aria-hidden="true" /> : null}
        {t(`detail.sources.relations.types.${type}`)}
      </span>
      <div className="grid gap-2 sm:grid-cols-2">
        <RelationSide side={relation.claim} label={t("detail.sources.relations.thisFile")} />
        <RelationSide side={relation.other} label={relation.other.sourceName} />
      </div>
      {relation.explanation ? (
        <p className="text-body-sm text-muted-foreground">{relation.explanation}</p>
      ) : null}
      {relation.reasons.length > 0 ? (
        <p className="text-micro text-muted-foreground">
          {t("detail.sources.relations.weakened", { reasons: relation.reasons.join("; ") })}
        </p>
      ) : null}
    </li>
  );
}

function RelationSide({ side, label }: { side: ClaimRelationSide; label: string }): React.JSX.Element {
  const { t } = useTranslation("projects");
  return (
    <div className="flex min-w-0 flex-col gap-1 border-l-2 border-border pl-3">
      {/* L'ancora sta col file: in una colonna stretta la citazione va a capo
          da sola, senza lasciare l'ancora orfana a fine riga. */}
      <p className="flex min-w-0 items-baseline gap-1.5 text-micro text-muted-foreground">
        <span className="truncate font-medium" title={label}>
          {label}
        </span>
        <span className="shrink-0 font-mono">{side.anchorRef}</span>
      </p>
      <p className="text-body-sm leading-relaxed text-foreground">{side.statement}</p>
      <p className="text-micro break-words text-muted-foreground">
        <q className="italic">{side.quote}</q>
        {side.quoteVerified ? null : (
          <span className="ml-1.5 text-[var(--color-status-warning)]">{t("detail.sources.claims.unverified")}</span>
        )}
      </p>
    </div>
  );
}

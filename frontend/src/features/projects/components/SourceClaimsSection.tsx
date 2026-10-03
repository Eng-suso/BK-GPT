import React from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, CircleAlert, Loader2 } from "lucide-react";

import type { ProjectSource } from "@/contracts/workspace";
import { useSourceClaimsQuery } from "../api";

/**
 * Cosa afferma una fonte, ognuna con la porzione che la sostiene (P1.12).
 *
 * L'estrazione parte da un gesto del consulente: la conferma, o l'invio del
 * file in chat. Prima di quel gesto la sezione dice come farla partire; durante,
 * che sta lavorando; dopo, le affermazioni con la loro ancora (`§2`, `R7`,
 * `Ordini!B7`) e la citazione, marcata quando non e' stata ritrovata parola per
 * parola.
 */
export function SourceClaimsSection({ source }: { source: ProjectSource }): React.JSX.Element | null {
  const { t } = useTranslation("projects");
  const claims = useSourceClaimsQuery(source.id, source.claimsStatus);

  // Le fonti senza file (interviste dalla chat) non passano da qui.
  if (source.acquisitionStatus === null) return null;

  let body: React.ReactNode;
  if (source.claimsStatus === null) {
    body = <p className="text-body-sm text-muted-foreground">{t("detail.sources.claims.notRequested")}</p>;
  } else if (source.claimsStatus === "pending") {
    body = (
      <p className="flex items-center gap-1.5 text-body-sm text-muted-foreground" role="status">
        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        {t("detail.sources.claims.pending")}
      </p>
    );
  } else if (source.claimsStatus === "failed") {
    body = (
      <p className="text-body-sm text-destructive" role="alert">
        {t("detail.sources.claims.failed", { reason: source.claimsError ?? "" })}
      </p>
    );
  } else if (claims.isLoading) {
    body = <p className="text-body-sm text-muted-foreground">{t("detail.sources.claims.loading")}</p>;
  } else if (!claims.data?.length) {
    body = <p className="text-body-sm text-muted-foreground">{t("detail.sources.claims.none")}</p>;
  } else {
    body = (
      <ol className="flex flex-col gap-2.5">
        {claims.data.map((claim) => (
          <li key={claim.id} className="flex flex-col gap-1 border-l-2 border-border pl-3">
            <p className="text-body-sm leading-relaxed text-foreground">{claim.statement}</p>
            <p className="flex flex-wrap items-baseline gap-x-1.5 text-micro text-muted-foreground">
              <span className="font-mono">{claim.anchorRef}</span>
              <span aria-hidden="true">·</span>
              <q className="italic">{claim.quote}</q>
              {claim.quoteVerified ? (
                <span className="inline-flex items-center gap-0.5 text-[var(--color-status-success)]">
                  <CheckCircle2 className="size-3" aria-hidden="true" />
                  {t("detail.sources.claims.verified")}
                </span>
              ) : (
                <span className="inline-flex items-center gap-0.5 text-[var(--color-status-warning)]">
                  <CircleAlert className="size-3" aria-hidden="true" />
                  {t("detail.sources.claims.unverified")}
                </span>
              )}
            </p>
          </li>
        ))}
      </ol>
    );
  }

  return (
    <section className="flex flex-col gap-1.5" aria-labelledby={`claims-${source.id}`}>
      <h3
        id={`claims-${source.id}`}
        className="text-micro font-medium tracking-wide text-muted-foreground uppercase"
      >
        {t("detail.sources.claims.heading")}
      </h3>
      {body}
      {source.claimsStatus === "done" && source.claimsError ? (
        <p className="text-micro text-[var(--color-status-warning)]">{source.claimsError}</p>
      ) : null}
    </section>
  );
}

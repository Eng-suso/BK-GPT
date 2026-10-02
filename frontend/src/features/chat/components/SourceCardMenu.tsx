import React from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { SourceRole } from "../../../contracts/workspace";

const ROLES: SourceRole[] = ["context", "process_evidence", "policy", "operational_data"];

type SourceCardMenuProps = {
  fileName: string;
  roles: SourceRole[];
  /** I ruoli che il nome del file suggerisce, quando sono diversi da quelli attuali. */
  suggestion: SourceRole[] | null;
  onApply: (roles: SourceRole[]) => void;
  /** Toglie la card dal messaggio lasciando il file tra le Fonti. */
  onKeep: () => void;
  disabled?: boolean;
};

/**
 * A cosa serve un file caricato dal composer, sulla sua card.
 *
 * DeliR propone il ruolo dal nome e dal formato ("Sembra: Regole da
 * rispettare"); il consulente lo accetta o lo cambia con un clic. Dallo stesso
 * menu il file si tiene tra le Fonti senza mandarlo con il messaggio.
 */
export function SourceCardMenu({
  fileName,
  roles,
  suggestion,
  onApply,
  onKeep,
  disabled,
}: SourceCardMenuProps): React.JSX.Element {
  const { t } = useTranslation("chat");
  const { t: tProjects } = useTranslation("projects");
  const labels = (values: SourceRole[]) =>
    values.map((role) => tProjects(`detail.sources.roles.${role}`)).join(", ");
  const current = roles.length > 0 ? labels(roles) : t("card.noRoles");
  const trigger = suggestion ? t("card.suggested", { roles: labels(suggestion) }) : current;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            "composer-chip-role",
            suggestion && "is-suggested",
          )}
          // Il nome dice file, ruolo attuale e, se c'e', la proposta.
          aria-label={t("card.menuLabel", { file: fileName, roles: trigger })}
        >
          <span className="composer-chip-role-text">{trigger}</span>
          <ChevronDown aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="min-w-56">
        <DropdownMenuLabel>{t("card.rolesLabel")}</DropdownMenuLabel>
        {suggestion ? (
          <DropdownMenuItem onSelect={() => onApply(suggestion)}>
            {t("card.useSuggestion", { roles: labels(suggestion) })}
          </DropdownMenuItem>
        ) : null}
        {ROLES.map((role) => {
          const checked = roles.includes(role);
          return (
            <DropdownMenuCheckboxItem
              key={role}
              checked={checked}
              // Almeno un ruolo: l'ultimo non si toglie.
              disabled={checked && roles.length === 1}
              onSelect={(event) => event.preventDefault()}
              onCheckedChange={(next) =>
                onApply(next ? [...roles, role] : roles.filter((item) => item !== role))
              }
            >
              {tProjects(`detail.sources.roles.${role}`)}
            </DropdownMenuCheckboxItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onKeep}>{t("card.keep")}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

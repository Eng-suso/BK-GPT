import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Flag } from "lucide-react";

import { EmptyState } from "@/components/feedback";
import { Meter } from "@/components/data";
import { Checkbox } from "@/ui/checkbox";
import { cn } from "@/lib/utils";
import type { Milestone } from "@/contracts/workspace";
import { useSetProjectMilestonesMutation } from "../api";

/**
 * Formats the date a milestone was reached, in the reader's locale.
 *
 * @param value - ISO 8601 timestamp written by the backend
 * @param locale - Active i18n language
 * @returns The formatted date, or the raw value when it cannot be parsed
 */
function formatReachedOn(value: string, locale: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleDateString(locale, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/**
 * The engagement's milestones, and which of them have been reached.
 *
 * The list used to be five lines of text with a tick on the first entry and a
 * clock on the second — state read off the array index, not off the record.
 * Here every milestone carries its own state, and the consultant marks one
 * reached from the same row that shows it.
 *
 * @param projectId - The project whose milestones are shown
 * @param milestones - The milestones as the record holds them
 * @returns The milestone tracker section
 */
export function MilestoneTracker({
  projectId,
  milestones,
}: {
  projectId: string;
  milestones: Milestone[];
}): React.JSX.Element {
  const { t, i18n } = useTranslation("projects");
  const [failed, setFailed] = useState(false);
  const setMilestones = useSetProjectMilestonesMutation(projectId);

  const reached = useMemo(
    () => milestones.filter((milestone) => milestone.status === "done").length,
    [milestones],
  );

  const toggle = (index: number, done: boolean) => {
    setFailed(false);
    setMilestones.mutate(
      milestones.map((milestone, i) =>
        i === index
          ? {
              ...milestone,
              status: done ? "done" : "planned",
              // La data la scrive il backend: qui si dichiara solo lo stato.
              completedAt: done ? milestone.completedAt : null,
            }
          : milestone,
      ),
      { onError: () => setFailed(true) },
    );
  };

  if (milestones.length === 0) {
    return (
      <EmptyState
        variant="inline"
        icon={Flag}
        title={t("detail.milestones.empty")}
        description={t("detail.milestones.emptyDescription")}
      />
    );
  }

  const percent = Math.round((reached / milestones.length) * 100);

  return (
    <div className="flex flex-col gap-3 pt-3">
      <div className="flex items-center gap-3">
        <Meter
          value={percent}
          label={t("detail.milestones.progressLabel")}
          showValue={false}
          height={5}
          className="max-w-[220px] flex-1"
        />
        <span className="text-xs font-medium tabular-nums text-muted-foreground">
          {t("detail.milestones.reached", {
            done: reached,
            total: milestones.length,
          })}
        </span>
      </div>

      <ul className="flex flex-col">
        {milestones.map((milestone, index) => {
          const done = milestone.status === "done";
          const id = `milestone-${projectId}-${index}`;
          return (
            <li
              key={`${milestone.title}-${index}`}
              className="flex items-start gap-2.5 border-b border-border/60 py-2.5 last:border-b-0"
            >
              <Checkbox
                id={id}
                checked={done}
                disabled={setMilestones.isPending}
                onCheckedChange={(checked) => toggle(index, checked === true)}
                className="mt-0.5"
              />
              <label
                htmlFor={id}
                className={cn(
                  "min-w-0 cursor-pointer text-body-sm leading-snug",
                  done ? "text-muted-foreground" : "text-foreground",
                  setMilestones.isPending && "cursor-progress opacity-70",
                )}
              >
                {milestone.title}
                <span className="mt-0.5 block text-micro text-muted-foreground">
                  {done && milestone.completedAt
                    ? t("detail.milestones.reachedOn", {
                        date: formatReachedOn(
                          milestone.completedAt,
                          i18n.language,
                        ),
                      })
                    : done
                      ? t("detail.milestones.reachedNoDate")
                      : t("detail.milestones.planned")}
                </span>
              </label>
            </li>
          );
        })}
      </ul>

      <p
        role={failed ? "alert" : undefined}
        aria-live="polite"
        className={cn(
          "text-micro",
          failed ? "text-[var(--color-status-danger)]" : "text-muted-foreground",
        )}
      >
        {failed
          ? t("detail.milestones.error")
          : setMilestones.isPending
            ? t("detail.milestones.saving")
            : ""}
      </p>
    </div>
  );
}

import { useTranslation } from "react-i18next";
import { Flag, GitFork, Hourglass, Play, Split, UserRound } from "lucide-react";

import { Surface } from "@/ui/surface";
import type { PlainNext, PlainProcess, PlainStep } from "./plainProcess";

const KIND_ICON = { decision: GitFork, parallel: Split, wait: Hourglass } as const;

/**
 * Il processo per chi non ha mai visto un diagramma: inizio, passi numerati
 * con chi li fa, decisioni come domande con le risposte, fine. I passi che la
 * consegna cambia portano l'etichetta "Cambia" e cosa cambia.
 */
export function PlainProcessSection({ plain, changedTitles }: {
  plain: PlainProcess;
  /** Per ogni passo toccato da una modifica, il titolo delle modifiche. */
  changedTitles: Map<string, string[]>;
}): React.JSX.Element {
  const { t } = useTranslation("process");
  const k = (key: string, options?: Record<string, unknown>) => t(`handover.dashboard.plain.${key}`, options);

  return (
    <section className="handover-section" aria-labelledby="owner-plain">
      <header className="handover-section-heading">
        <h2 id="owner-plain">{k("title")}</h2>
        <p>{k("description")}</p>
      </header>
      {plain.steps.length === 0 ? (
        <Surface variant="inset" className="handover-empty">{k("empty")}</Surface>
      ) : <>
        {plain.actors.length > 0 && (
          <div className="plain-people" aria-label={k("people")}>
            <span className="plain-people-label">{k("people")}</span>
            <ul>{plain.actors.map((actor) => (
              <li key={actor.name}><UserRound aria-hidden className="size-3.5" />{actor.name}<span>· {k("peopleSteps", { count: actor.steps })}</span></li>
            ))}</ul>
          </div>
        )}
        <Surface asChild variant="panel"><ol className="plain-steps">
          <li className="plain-step" data-kind="start">
            <span className="plain-step-marker" aria-hidden><Play className="size-3.5" /></span>
            <div className="plain-step-body"><p className="plain-step-kicker">{k("startsWhen")}</p><p className="plain-step-name">{plain.starts.filter(Boolean).join(" · ") || k("unnamedStart")}</p></div>
          </li>
          {plain.steps.map((step) => <Step key={step.id} step={step} changes={changedTitles.get(step.id) ?? []} />)}
          <li className="plain-step" data-kind="end">
            <span className="plain-step-marker" aria-hidden><Flag className="size-3.5" /></span>
            <div className="plain-step-body"><p className="plain-step-kicker">{k("endsWith")}</p><p className="plain-step-name">{plain.ends.filter(Boolean).join(" · ") || k("unnamedEnd")}</p></div>
          </li>
        </ol></Surface>
      </>}
    </section>
  );
}

function Step({ step, changes }: { step: PlainStep; changes: string[] }): React.JSX.Element {
  const { t } = useTranslation("process");
  const k = (key: string, options?: Record<string, unknown>) => t(`handover.dashboard.plain.${key}`, options);
  const Icon = step.kind === "activity" ? null : KIND_ICON[step.kind];
  const name = step.name || (step.kind === "decision" ? k("unnamedDecision") : step.kind === "parallel" ? k("parallel") : k("unnamed"));
  const branching = step.kind === "decision" || step.kind === "parallel" || step.next.length > 1;
  const target = (next: PlainNext) => next.kind === "end" ? k("toEnd") : k("toStep", { n: next.number });
  // Un passo che porta al successivo non ha bisogno di dirlo: si legge in ordine.
  const single = step.next.length === 1 ? step.next[0] : null;
  const jump = single && !(single.kind === "step" && single.number === step.number + 1)
    ? (single.kind === "end" ? k("thenEnd") : k("then", { n: single.number })) : null;

  return (
    <li id={`plain-step-${step.number}`} className="plain-step" data-kind={step.kind} data-changed={changes.length > 0 || undefined}>
      <span className="plain-step-marker" aria-hidden>{Icon ? <Icon className="size-3.5" /> : step.number}</span>
      <div className="plain-step-body">
        <p className="plain-step-kicker">
          {k("step", { n: step.number })}
          {step.kind === "decision" && <> · {k("decision")}</>}
          {step.kind === "wait" && <> · {k("wait")}</>}
          {changes.length > 0 && <span className="plain-step-changed">{k("changed")}</span>}
        </p>
        <p className="plain-step-name">{name}</p>
        {step.kind !== "parallel" && step.kind !== "decision" && (
          <p className="plain-step-who"><UserRound aria-hidden className="size-3.5" /><span className="sr-only">{k("who")}: </span>{step.actor || k("nobody")}</p>
        )}
        {changes.map((title) => <p key={title} className="plain-step-change">{title}</p>)}
        {branching && step.next.length > 0 && (
          <ul className="plain-step-branches">
            {step.next.map((next, index) => (
              <li key={`${index}-${target(next)}`}>
                <span className="plain-step-answer">{next.label ? k("answer", { label: next.label }) : k("path", { index: index + 1 })}</span>
                <span aria-hidden> → </span>{target(next)}
              </li>
            ))}
          </ul>
        )}
        {!branching && jump && <p className="plain-step-jump">{jump}</p>}
      </div>
    </li>
  );
}

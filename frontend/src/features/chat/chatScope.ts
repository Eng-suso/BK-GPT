import type { ChatScope } from "../../contracts/chat";

export type { ChatScope };

/** Full label, e.g. "Chat canvas - Idem Process". Kept for existing call sites. */
export function titleForScope(scope: ChatScope) {
  if (scope.type === "project") return `Chat progetto - ${scope.projectName}`;
  if (scope.type === "process") return `Chat processo - ${scope.processName}`;
  if (scope.type === "canvas") return `Chat canvas - ${scope.processName}`;
  return "Chat consulente";
}

/**
 * What the chat is *about* — the process / project name, or a plain label for
 * the portfolio-wide assistant. Used as the panel-header title before a
 * conversation has its own title.
 */
export function subjectForScope(scope: ChatScope, consultantLabel: string) {
  if (scope.type === "project") return scope.projectName;
  if (scope.type === "process" || scope.type === "canvas") return scope.processName;
  return consultantLabel;
}

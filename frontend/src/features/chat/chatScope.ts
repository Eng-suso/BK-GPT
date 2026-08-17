import type { ChatScope } from "../../contracts/chat";

export type { ChatScope };

export function titleForScope(scope: ChatScope) {
  if (scope.type === "project") return `Chat progetto - ${scope.projectName}`;
  if (scope.type === "process") return `Chat processo - ${scope.processName}`;
  if (scope.type === "canvas") return `Chat canvas - ${scope.processName}`;
  return "Chat consulente";
}

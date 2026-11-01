import type { ReactNode } from "react";
import { ChevronDown, CircleAlert } from "lucide-react";
import { Surface } from "@/ui/surface";

/** A visible status with details available without interrupting the form. */
export function DisclosureNotice({ title, children }: { title: string; children: ReactNode }) {
  return <Surface asChild variant="inset"><details className="ui-disclosure-notice">
    <summary><CircleAlert aria-hidden="true" className="size-4 shrink-0 text-warning" /><span>{title}</span><ChevronDown aria-hidden="true" className="ml-auto size-4 shrink-0" /></summary>
    <div>{children}</div>
  </details></Surface>;
}

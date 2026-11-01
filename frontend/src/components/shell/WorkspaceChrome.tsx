import { createContext, useContext, type ReactNode } from "react";
import { PanelsTopLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/ui/popover";

const WorkspaceChromeContext = createContext<ReactNode>(null);
export function WorkspaceChromeProvider({ children, value }: { children: ReactNode; value: ReactNode }) {
  return <WorkspaceChromeContext.Provider value={value}>{children}</WorkspaceChromeContext.Provider>;
}

/** Global tools stay available without taking another row from the canvas. */
export function WorkspaceGlobalTools() {
  const tools = useContext(WorkspaceChromeContext);
  const { t } = useTranslation("common");
  if (!tools) return null;
  return <Popover><PopoverTrigger asChild><Button variant="ghost" size="icon" aria-label={t("nav.tools")} title={t("nav.tools")}><PanelsTopLeft aria-hidden="true" /></Button></PopoverTrigger><PopoverContent align="end" className="w-auto max-w-[calc(100vw-2rem)] p-2">{tools}</PopoverContent></Popover>;
}

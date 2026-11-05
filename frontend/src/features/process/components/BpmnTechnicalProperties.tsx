import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Input } from "@/ui/input";
import type { SelectedBpmnElement } from "../bpmn/types";
export function BpmnTechnicalProperties({ element, onNameChange }: {
    element: SelectedBpmnElement | null;
    onNameChange: (name: string) => void;
}) {
    const { t } = useTranslation("process"), id = useId();
    if (!element)
        return <p className="p-4 text-sm text-muted-foreground">{t("properties.vendor.noSelection")}</p>;
    return <div className="grid gap-4 p-4">
  <div><span className="text-xs text-muted-foreground">ID</span><p className="break-all text-sm">{element.id}</p></div>
  <div><span className="text-xs text-muted-foreground">BPMN</span><p className="text-sm">{element.type}</p></div>
  <div className="grid gap-2"><label htmlFor={id} className="text-sm">{t("properties.enterprise.name")}</label><Input id={id} value={element.name} onChange={event => onNameChange(event.target.value)}/></div>
 </div>;
}

import {useTranslation} from "react-i18next";
import {DropdownMenuLabel,DropdownMenuRadioGroup,DropdownMenuRadioItem} from "@/ui/dropdown-menu";
import type {CreationTool} from "../bpmn/elements";
import {BpmnToolIcon} from "./BpmnToolIcon";

/** One accessible type picker for both pointer entry points. */
export function BpmnTypeOptions({actions,onAction}:{actions:CreationTool[];onAction:(id:string,event:Event)=>void}) {
  const {t}=useTranslation("process");
  return <>
    <DropdownMenuLabel>{t("canvas.interactions.replace")}</DropdownMenuLabel>
    <DropdownMenuRadioGroup aria-label={t("canvas.interactions.replace")} value={actions.find(action=>action.checked)?.id??""}>
      {actions.map(action=><DropdownMenuRadioItem className="min-h-9 gap-3" key={action.id} value={action.id} textValue={action.title} onSelect={event=>onAction(action.id,event)}>
        <BpmnToolIcon id={action.id}/><span>{action.title}</span>
      </DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
  </>;
}

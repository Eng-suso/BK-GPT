import { ArrowUpRight, Hand, MousePointer2, Scan, UnfoldHorizontal, Trash2, Settings2 } from "lucide-react";


/** UI glyphs only. Diagram shapes and serialized BPMN are owned by the modeler. */
export function BpmnToolIcon({ id }: { id: string }) {
  if (id === "select") return <MousePointer2 aria-hidden />;
  if (id === "hand-tool") return <Hand aria-hidden />;
  if (id === "lasso-tool") return <Scan aria-hidden />;
  if (id === "space-tool") return <UnfoldHorizontal aria-hidden />;
  if (/connect/.test(id)) return <ArrowUpRight aria-hidden />;
  if (/delete|remove/.test(id)) return <Trash2 aria-hidden />;
  if (/replace/.test(id)) return <Settings2 aria-hidden />;
  const gateway = /gateway/.test(id);
  const event = /event|create\.(start|end|catch|throw|boundary)-/.test(id);
  const end = /end/.test(id);
  const intermediate = /intermediate|catch|throw|boundary/.test(id);
  const lane = /participant|lane/.test(id);
  const data = /data-object|data-store/.test(id);
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="size-5 shrink-0">
    {gateway ? <><path d="m12 2 10 10-10 10L2 12Z" />{/parallel/.test(id) ? <path d="M8 12h8m-4-4v8" /> : /inclusive/.test(id) ? <circle cx="12" cy="12" r="4" /> : <path d="m9 9 6 6m0-6-6 6" />}</>
      : event ? <><circle cx="12" cy="12" r="9" strokeWidth={end ? 3 : 1.5} />{intermediate && <circle cx="12" cy="12" r="6.5" />}{/timer/.test(id) && <path d="M12 7v5l3 2" />}{/message/.test(id) && <><rect x="7" y="8" width="10" height="8" rx=".5" /><path d="m7 8 5 4 5-4" /></>}</>
      : lane ? <><rect x="2" y="3" width="20" height="18" rx="2" /><path d="M7 3v18M7 12h15" /></>
      : data ? <><path d="M6 2h8l4 4v16H6Z" /><path d="M14 2v5h4M9 12h6m-6 4h6" /></>
      : /annotation/.test(id) ? <path d="M9 3H5v18h4M10 8h10m-10 4h10m-10 4h7" />
      : <><rect x="2" y="4" width="20" height="16" rx="4" strokeDasharray={/group/.test(id) ? "3 3" : undefined} />{/subprocess|call-activity/.test(id) && <path d="M9 16h6m-3-3v6" />}{/user/.test(id) && <><circle cx="8" cy="9" r="2" /><path d="M5 15v-1a3 3 0 0 1 6 0v1" /></>}{/service|script|business-rule/.test(id) && <path d="m7 9-2 3 2 3m10-6 2 3-2 3m-4-7-2 8" />}</>}
  </svg>;
}

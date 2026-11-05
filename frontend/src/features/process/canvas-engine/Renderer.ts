import type { Bus, CanvasElement } from "./types";
const SVG = "http://www.w3.org/2000/svg";
function node(tag: string, attrs: Record<string, string | number> = {}, parent?: SVGElement) { const el = document.createElementNS(SVG, tag); for (const [key, value] of Object.entries(attrs))
    el.setAttribute(key, String(value)); parent?.append(el); return el; }
export function shapePath(el: CanvasElement): string {
    const { x, y, width: w, height: h } = el;
    if (/Event$/.test(el.type)) {
        const r = Math.min(w, h) / 2;
        return "M" + (x + w / 2 - r) + "," + (y + h / 2) + "a" + r + "," + r + " 0 1,0 " + (r * 2) + ",0a" + r + "," + r + " 0 1,0 -" + (r * 2) + ",0";
    }
    if (/Gateway$/.test(el.type))
        return "M" + (x + w / 2) + "," + y + "L" + (x + w) + "," + (y + h / 2) + "L" + (x + w / 2) + "," + (y + h) + "L" + x + "," + (y + h / 2) + "Z";
    if (/Task$|Activity$|SubProcess$/.test(el.type)) {
        const r=Math.min(12,w/2,h/2);
        return "M"+(x+r)+","+y+"H"+(x+w-r)+"Q"+(x+w)+","+y+" "+(x+w)+","+(y+r)+"V"+(y+h-r)+"Q"+(x+w)+","+(y+h)+" "+(x+w-r)+","+(y+h)+"H"+(x+r)+"Q"+x+","+(y+h)+" "+x+","+(y+h-r)+"V"+(y+r)+"Q"+x+","+y+" "+(x+r)+","+y+"Z";
    }
    return "M" + x + "," + y + "h" + w + "v" + h + "h-" + w + "Z";
}
function text(parent: SVGElement, value: string, x: number, y: number, width: number, fontSize = 14, anchor = "middle") {
    const max = Math.max(4, Math.floor(width / (fontSize * .51))), lines: string[] = [];
    for (const paragraph of value.split("\n")) {
        let line = "";
        for (const word of paragraph.split(/\s+/)) {
            if (line && (line + " " + word).length > max) {
                lines.push(line);
                line = word;
            }
            else
                line += (line ? " " : "") + word;
        }
        lines.push(line);
    }
    const label = node("text", { "font-size": fontSize, "font-family": "var(--font-family-geist, sans-serif)", "text-anchor": anchor, fill: "var(--color-text-primary)", class: "delir-node-label" }, parent);
    lines.forEach((line, index) => { const span = node("tspan", { x, y: y + (index - (lines.length - 1) / 2) * fontSize * 1.3 }, label); span.textContent = line + (index < lines.length - 1 ? " " : ""); });
    return label;
}
/** Original DeliR BPMN graphics. Generic diagram-js supplies SVG lifecycle only. */
export class DeliRRenderer {
    static $inject = ["eventBus"];
    constructor(bus: Bus) {
        bus.on("render.shape", 2000, (_event, context) => { const { element, gfx } = context as {
            element: CanvasElement;
            gfx: SVGElement;
        }; const body = this.drawShape(gfx, element);
        gfx.parentElement?.setAttribute("data-delir-type", element.type);
        gfx.querySelectorAll("text").forEach(label => label.setAttribute("data-delir-label-for", element.labelTarget?.id ?? element.id));
        return body; });
        bus.on("render.connection", 2000, (_event, context) => { const { element, gfx } = context as {
            element: CanvasElement;
            gfx: SVGElement;
        }; return this.drawConnection(gfx, element); });
        bus.on("render.getShapePath", 2000, (_event, element) => shapePath(element as CanvasElement));
        bus.on("render.getConnectionPath", 2000, (_event, element) => (element as CanvasElement).waypoints?.map((p, i) => (i ? "L" : "M") + p.x + "," + p.y).join("") ?? "");
    }
    drawShape(gfx: SVGElement, el: CanvasElement) {
        const w = el.width, h = el.height, t = el.type, fill = el.di?.get("bioc:fill") || el.di?.get("color:background-color") || "var(--color-surface-primary)", stroke = el.di?.get("bioc:stroke") || el.di?.get("color:border-color") || "var(--domain-process-task-border)";
        if (t === "label")
            return text(gfx, el.businessObject.name ?? "", w / 2, h / 2, w, 12);
        let body: SVGElement;
        const common = { fill, stroke, "stroke-width": 1.5, "stroke-linejoin": "round" };
        if (/Event$/.test(t)) {
            body = node("circle", { cx: w / 2, cy: h / 2, r: Math.min(w, h) / 2 - 1, ...common, "stroke-width": /EndEvent$/.test(t) ? 3 : 1.5, "stroke-dasharray": el.businessObject.isInterrupting === false ? "4 3" : "" }, gfx);
            if (/Intermediate|Boundary/.test(t))
                node("circle", { cx: w / 2, cy: h / 2, r: Math.min(w, h) / 2 - 4, fill: "none", stroke, "stroke-width": 1 }, gfx);
            const definition = String(el.businessObject.eventDefinitions?.[0]?.$type ?? "");
            if (/Timer/.test(definition)) {
                node("circle", { cx: w / 2, cy: h / 2, r: w * .23, fill: "none", stroke, "stroke-width": 1.2 }, gfx);
                node("path", { d: "M" + w / 2 + "," + h * .32 + "v" + h * .18 + "l" + w * .14 + "," + h * .1, fill: "none", stroke, "stroke-width": 1.2 }, gfx);
            }
            else if (/Message/.test(definition)) {
                node("rect", { x: w * .23, y: h * .32, width: w * .54, height: h * .36, fill: "none", stroke }, gfx);
                node("path", { d: "M" + w * .23 + "," + h * .32 + "l" + w * .27 + "," + h * .2 + "l" + w * .27 + ",-" + h * .2, fill: "none", stroke }, gfx);
            }
            else if (/Terminate/.test(definition))
                node("circle", { cx: w / 2, cy: h / 2, r: w * .25, fill: stroke }, gfx);
            else if (/Signal/.test(definition))
                node("path", { d: "M" + w / 2 + "," + h * .25 + "L" + w * .75 + "," + h * .7 + "L" + w * .25 + "," + h * .7 + "Z", fill: /Throw|End/.test(t) ? stroke : "none", stroke }, gfx);
            else if (/Error/.test(definition))
                node("path", { d: "M" + w * .6 + "," + h * .2 + "L" + w * .3 + "," + h * .53 + "H" + w * .5 + "L" + w * .4 + "," + h * .8 + "L" + w * .72 + "," + h * .45 + "H" + w * .52 + "Z", fill: stroke }, gfx);
            else if (/Escalation/.test(definition))
                node("path", { d: "M" + w * .3 + "," + h * .72 + "L" + w * .5 + "," + h * .25 + "L" + w * .7 + "," + h * .72 + "L" + w * .5 + "," + h * .55 + "Z", fill: /Throw|End/.test(t) ? stroke : "none", stroke }, gfx);
            else if (/Cancel/.test(definition))
                node("path", { d: "M" + w * .3 + "," + h * .3 + "L" + w * .7 + "," + h * .7 + "M" + w * .7 + "," + h * .3 + "L" + w * .3 + "," + h * .7, stroke, "stroke-width": 3 }, gfx);
            else if (/Link/.test(definition))
                node("path", { d: "M" + w * .25 + "," + h * .4 + "H" + w * .55 + "V" + h * .25 + "L" + w * .8 + "," + h * .5 + "L" + w * .55 + "," + h * .75 + "V" + h * .6 + "H" + w * .25 + "Z", fill: /Throw/.test(t) ? stroke : "none", stroke }, gfx);
            else if (/Compensate/.test(definition))
                node("path", { d: "M" + w * .48 + "," + h * .3 + "L" + w * .25 + "," + h * .5 + "L" + w * .48 + "," + h * .7 + "ZM" + w * .72 + "," + h * .3 + "L" + w * .49 + "," + h * .5 + "L" + w * .72 + "," + h * .7 + "Z", fill: /Throw|End/.test(t) ? stroke : "none", stroke }, gfx);
            else if (/Conditional/.test(definition)) {
                node("rect", { x: w * .3, y: h * .23, width: w * .4, height: h * .54, fill: "none", stroke }, gfx);
                for (const offset of [.36, .49, .62])
                    node("path", { d: "M" + w * .36 + "," + h * offset + "H" + w * .64, stroke }, gfx);
            }
        }
        else if (/Gateway$/.test(t)) {
            body = node("polygon", { points: w / 2 + ",1 " + (w - 1) + "," + h / 2 + " " + w / 2 + "," + (h - 1) + " 1," + h / 2, ...common }, gfx);
            if (/EventBased/.test(t)) {
                node("circle", { cx: w / 2, cy: h / 2, r: w * .26, fill: "none", stroke }, gfx);
                node("polygon", { points: w / 2 + "," + h * .31 + " " + w * .68 + "," + h * .44 + " " + w * .61 + "," + h * .65 + " " + w * .39 + "," + h * .65 + " " + w * .32 + "," + h * .44, fill: "none", stroke }, gfx);
            }
            else if (/Complex/.test(t)) {
                for (const angle of [0, 45, 90, 135])
                    node("path", { d: "M" + w * .28 + "," + h / 2 + "H" + w * .72, transform: "rotate(" + angle + " " + w / 2 + " " + h / 2 + ")", stroke, "stroke-width": 2.1 }, gfx);
            }
            else if (/Inclusive/.test(t))
                node("circle", { cx: w / 2, cy: h / 2, r: w * .23, fill: "none", stroke, "stroke-width": 2 }, gfx);
            else
                node("path", { d: /Parallel/.test(t) ? "M" + w * .27 + "," + h / 2 + "H" + w * .73 + "M" + w / 2 + "," + h * .27 + "V" + h * .73 : "M" + w * .32 + "," + h * .32 + "L" + w * .68 + "," + h * .68 + "M" + w * .68 + "," + h * .32 + "L" + w * .32 + "," + h * .68, stroke, "stroke-width": 2.6, "stroke-linecap": "round" }, gfx);
        }
        else if (/Participant|Lane/.test(t)) {
            body = node("rect", { width: w, height: h, ...common, "stroke-width": 1 }, gfx);
            // The participant has a separate title band. A leaf lane label is
            // inside its partition, without another separating vertical line
            // (BPMN 2.0.2 §10.8). Nested lane borders provide their own divider.
            if(t === "bpmn:Participant")node("path", { d: "M30 0V" + h, stroke, "stroke-width": 1 }, gfx);
            const label = text(gfx, el.businessObject.name ?? "", 0, 0, Math.max(100, h - 24), 13);
            label.setAttribute("transform", "translate(19," + h / 2 + ") rotate(-90)");
            return body;
        }
        else if (/TextAnnotation/.test(t)) {
            body = node("path", { d: "M12 0H0V" + h + "H12", fill: "none", stroke, "stroke-width": 1.5 }, gfx);
            text(gfx, el.businessObject.name ?? "", 12, h / 2, w - 24, 13, "start");
            return body;
        }
        else if (/DataStore/.test(t)) {
            body = node("path", { d: "M1 10A" + w / 2 + " 9 0 0 1 " + (w - 1) + " 10V" + (h - 10) + "A" + w / 2 + " 9 0 0 1 1 " + (h - 10) + "ZM1 10A" + w / 2 + " 9 0 0 0 " + (w - 1) + " 10", ...common }, gfx);
        }
        else if (/DataObject/.test(t)) {
            body = node("path", { d: "M1 1H" + (w - 12) + "L" + (w - 1) + " 12V" + (h - 1) + "H1ZM" + (w - 12) + " 1V12H" + (w - 1), ...common }, gfx);
        }
        else {
            body = node("rect", { width: w, height: h, rx: 12, ...common, "stroke-width": /CallActivity/.test(t) ? 3 : 1.5, "stroke-dasharray": /Group/.test(t) ? "6 4" : "" }, gfx);
            const icon = node("g", { transform: "translate(10,9)", fill: "none", stroke, "stroke-width": 1.2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" }, gfx);
            if (/UserTask/.test(t)) {
                node("circle", { cx: 6, cy: 3.5, r: 2.5 }, icon);
                node("path", { d: "M1 13v-2a5 5 0 0 1 10 0v2M3 10v3m6-3v3" }, icon);
            }
            else if (/ServiceTask/.test(t)) {
                node("path", { d: "m6 0 1 2 2 1 2-1 2 3-2 2v2l2 1-2 3-2-1-2 1-1 2H3l-1-2-2-1v-3l2-1V5L0 3 2 1l2 1Z" }, icon);
                node("circle", { cx: 6, cy: 7, r: 2.5 }, icon);
            }
            else if (/ScriptTask/.test(t)) {
                node("path", { d: "M2 0h9l2 3v11H2ZM5 5h5M5 8h5M5 11h4" }, icon);
            }
            else if (/BusinessRuleTask/.test(t)) {
                node("rect", { x: 0, y: 1, width: 14, height: 12, rx: 1 }, icon);
                node("path", { d: "M0 5h14M4 1v12M0 9h14" }, icon);
            }
            else if (/SendTask|ReceiveTask/.test(t)) {
                node("rect", { x: 0, y: 2, width: 14, height: 10, fill: /Send/.test(t) ? stroke : "none" }, icon);
                node("path", { d: "m0 2 7 6 7-6", stroke: /Send/.test(t) ? fill : stroke }, icon);
            }
            else if (/ManualTask/.test(t)) {
                node("path", { d: "M3 13 1 7l2-1 2 3V2h2v5-6h2v6-5h2v6-4h2v7l-2 3Z" }, icon);
            }
            if (/CallActivity/.test(t) || /SubProcess/.test(t) && el.di?.get("isExpanded") !== "true") {
                node("rect", { x: w / 2 - 6, y: h - 15, width: 12, height: 12, rx: 2, fill, stroke }, gfx);
                node("path", { d: "M" + (w / 2 - 3) + "," + (h - 9) + "h6M" + w / 2 + "," + (h - 12) + "v6", stroke }, gfx);
            }
        }

        if (/Task$|Activity$|SubProcess$/.test(t)) {
            const kind = el.businessObject.loopKind, y = h - 9, x = w / 2;
            if (kind === "parallel" || kind === "sequential") {
                for (const offset of [-4,0,4]) node("path", { d: kind === "parallel" ? "M"+(x+offset)+","+(y-5)+"v10" : "M"+(x-5)+","+(y+offset)+"h10", stroke, "stroke-width":1.4 }, gfx);
            } else if (kind === "loop") node("path", { d:"M"+(x+4)+","+(y+3)+"a5,5 0 1,1 0,-6m0 -3v4h-4", fill:"none", stroke, "stroke-width":1.3 }, gfx);
            if(el.businessObject.isForCompensation) node("path", { d:"M"+(x-12)+","+(y-5)+"l-6 5 6 5Zm-7 0-6 5 6 5Z", fill:"none", stroke }, gfx);
        }
        if (el.businessObject.name && !/Event$|Gateway$/.test(t))
            text(gfx, el.businessObject.name, w / 2, /SubProcess/.test(t) && el.di?.get("isExpanded") === "true" ? 20 : h / 2 + 4, w - 24, 14);
        return body;
    }
    drawConnection(gfx: SVGElement, el: CanvasElement) {
        const path = el.waypoints?.map((p, i) => (i ? "L" : "M") + p.x + "," + p.y).join("") ?? "";
        const stroke = el.di?.get("bioc:stroke") || "var(--color-text-secondary)";
        const body = node("path", { d: path, fill: "none", stroke, "stroke-width": 1.5, "stroke-linecap": "round", "stroke-linejoin": "round", "stroke-dasharray": /MessageFlow/.test(el.type) ? "8 5" : /Association/.test(el.type) ? "2 5" : "", class: /MessageFlow/.test(el.type) ? "delir-dashed-flow" : /Association/.test(el.type) ? "delir-dashed-flow delir-dashed-flow--association" : "" }, gfx);
        const points = el.waypoints ?? [];
        if (points.length > 1 && el.type === "bpmn:SequenceFlow" && (el.businessObject.isDefaultFlow || el.businessObject.hasCondition && /Task$|Activity$|SubProcess$/.test(el.source?.type ?? ""))) {
            const start = points[0], next = points[1], angle = Math.atan2(next.y-start.y,next.x-start.x)*180/Math.PI;
            node("path", {d:el.businessObject.isDefaultFlow ? "M7 -5 13 5" : "M0 0 6 -4 12 0 6 4Z",transform:"translate("+start.x+","+start.y+") rotate("+angle+")",fill:el.businessObject.isDefaultFlow ? "none" : "var(--color-surface-primary)",stroke,"stroke-width":1.4},gfx);
        }
        if (points.length > 1 && el.type === "bpmn:MessageFlow") node("circle",{cx:points[0].x,cy:points[0].y,r:3.5,fill:"var(--color-surface-primary)",stroke,"stroke-width":1.2},gfx);
        if (points.length > 1 && el.type !== "bpmn:Association") {
            const end = points.at(-1)!, previous = points.at(-2)!, angle = Math.atan2(end.y - previous.y, end.x - previous.x) * 180 / Math.PI;
            node("path", { d: /Data(Input|Output)Association/.test(el.type) ? "M-9 -4.5 0 0 -9 4.5" : "M-9 -4.5 0 0 -9 4.5Z", transform: "translate(" + end.x + "," + end.y + ") rotate(" + angle + ")", fill: /Data(Input|Output)Association/.test(el.type) ? "none" : /MessageFlow/.test(el.type) ? "var(--color-surface-primary)" : stroke, stroke, "stroke-width": 1 }, gfx);
        }
        return body;
    }
}

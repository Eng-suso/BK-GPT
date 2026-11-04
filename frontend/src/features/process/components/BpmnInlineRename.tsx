import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

/** Edit the rendered label in place, keeping event labels outside their symbol. */
export function BpmnInlineRename({ target, host, onCommit, onCancel, onDone, onSave }: {
  target: { id: string; name: string };
  host: RefObject<HTMLDivElement | null>;
  onCommit: (id: string, name: string) => void;
  onCancel: () => void; onDone: () => void; onSave: () => void;
}) {
  const { t } = useTranslation("process");
  const input = useRef<HTMLTextAreaElement>(null), finished = useRef(false);
  const [position, setPosition] = useState({ left: 0, top: 0, width: 120, fontSize: 14, minHeight: 20 });
  const commit = (save = false) => {
    if (finished.current) return;
    finished.current = true;
    onCommit(target.id, input.current?.value ?? target.name); onDone();
    if (save) onSave();
  };
  const cancel = () => {
    if (finished.current) return;
    finished.current = true; onCancel(); onDone();
  };
  useLayoutEffect(() => {
    const container = host.current;
    if (!container) return;
    const text = container.querySelector<SVGTextElement>('[data-delir-label-for="' + CSS.escape(target.id) + '"]');
    const measure = () => {
      const bounds = container.getBoundingClientRect();
      const element = container.querySelector<SVGGElement>('[data-element-id="' + CSS.escape(target.id) + '"]');
      const body = element?.querySelector<SVGGraphicsElement>(".djs-visual > :first-child");
      if (!element || !body) return;
      const box = body.getBoundingClientRect(), label = text?.getBoundingClientRect();
      const matrix = element.getScreenCTM(), scale = Math.hypot(matrix?.a ?? 1, matrix?.b ?? 0);
      const external = /Event$|Gateway$|DataObjectReference$|DataStoreReference$/.test(element.dataset.delirType ?? "") || element.classList.contains("djs-connection");
      const fontSize = (text ? parseFloat(getComputedStyle(text).fontSize) : external ? 12 : 14) * scale;
      const width = Math.min(external ? Math.max(92 * scale, label?.width ?? 0) : Math.max(60, box.width - 24 * scale), bounds.width - 16);
      const center = label && label.width > 0 ? label.x + label.width / 2 : box.x + box.width / 2;
      const height = Math.max(fontSize * 1.3, label?.height ?? 0);
      const top = label && label.height > 0 ? label.y : external ? box.bottom + 6 * scale : box.y + box.height / 2 - height / 2;
      setPosition({ left: Math.max(8, Math.min(bounds.width - width - 8, center - bounds.x - width / 2)), top: Math.max(8, Math.min(bounds.height - height - 8, top - bounds.y)), width, fontSize, minHeight: height });
    };
    measure(); text?.setAttribute("data-delir-editing", "true");
    input.current?.focus(); input.current?.select();
    const observer = new ResizeObserver(measure); observer.observe(container);
    return () => { observer.disconnect(); text?.removeAttribute("data-delir-editing"); };
  }, [host, target.id]);
  const grow = () => { if (input.current) { input.current.style.height = "0px"; input.current.style.height = input.current.scrollHeight + "px"; } };
  useLayoutEffect(grow, [position]);
  if (!host.current) return null;
  return createPortal(<form className="process-inline-rename" aria-label={t("canvas.interactions.rename")} style={position} onSubmit={event => { event.preventDefault(); commit(); }}>
    <textarea ref={input} className="process-inline-rename-text" rows={1} defaultValue={target.name} aria-label={t("properties.enterprise.name")} onInput={grow} onBlur={() => commit()} spellCheck={false} onKeyDown={event => {
      event.stopPropagation();
      if (event.key === "Escape") { event.preventDefault(); cancel(); }
      else if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); commit(); }
      else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); commit(true); }
    }} />
  </form>, host.current);
}

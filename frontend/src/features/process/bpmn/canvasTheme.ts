/** bpmn-js renderer options that draw a diagram in DeliR colours and type.
 *
 * Without them bpmn-js paints every shape, lane, flow and label in pure black;
 * the editor, the Review and the simulation canvases share these instead. The
 * values are read from the design tokens on the canvas host, so a theme change
 * reaches the diagram too.
 */
export function canvasThemeOptions(host: HTMLElement) {
  const tokens = getComputedStyle(host);
  const token = (name: string) => tokens.getPropertyValue(name).trim();
  return {
    textRenderer: {
      defaultStyle: { fontFamily: token("--font-family-geist"), fontSize: Number.parseFloat(token("--font-size-300")) },
      externalStyle: { fontFamily: token("--font-family-geist"), fontSize: Number.parseFloat(token("--font-size-100")) },
    },
    bpmnRenderer: {
      defaultFillColor: token("--color-surface-primary"),
      defaultStrokeColor: token("--color-text-secondary"),
      defaultLabelColor: token("--color-text-primary"),
    },
  };
}

import React from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, RadialBar, RadialBarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ReplayEngine, ReplayFrame } from "../replay/replayEngine";
import { WIDGET_COLORS, formatMetric } from "./dashboardFormatting";
import { interpolateText } from "./dashboardExpressions";
import { resolveWidgetData, type DashboardWidget } from "./dashboardModel";

const COLORS = Object.values(WIDGET_COLORS);

export function WidgetView({ widget, engine, frame, activityId }: {
  widget: DashboardWidget; engine: ReplayEngine; frame: ReplayFrame; activityId: string;
}): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language.startsWith("it") ? "it" : "en";
  const data = resolveWidgetData(engine, frame, widget, activityId, lang);
  const color = WIDGET_COLORS[widget.color];
  const format = (value: number | null) => formatMetric(value, data.unit, lang);
  const clock = (seconds: number) => new Intl.DateTimeFormat(lang, { hour: "2-digit", minute: "2-digit" }).format(new Date(engine.startMs + seconds * 1000));
  const points = data.points.map((point) => ({ ...point, label: point.t === undefined ? point.label : clock(point.t) }));

  if (!data.expressionValid) return <div className="sim-widget-empty"><span>—</span><p>{t("simulation.studio.invalidMetricExpression")}</p></div>;
  if (widget.kind === "text") {
    const result = interpolateText(widget.text, {
      metric: data.value === null ? Number.NaN : data.value * (data.unit === "duration" ? 1000 : 1),
      total: frame.global.activeCases + frame.global.completedCases,
      currentTime: frame.global.clockMs,
    }, lang);
    return <div className="sim-note">
      {result.valid ? <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{result.text}</ReactMarkdown>
        : <p className="text-sm text-muted-foreground">{t(data.value === null ? "simulation.studio.noObservations" : "simulation.studio.invalidExpression")}</p>}
    </div>;
  }
  if (data.value === null) return <div className="sim-widget-empty"><span>—</span><p>{t("simulation.studio.noObservations")}</p></div>;

  if (widget.kind === "kpi") return <div className="sim-widget-kpi"><strong>{format(data.value)}</strong><p>{t(`simulation.studio.metric.${widget.metric}`)}</p></div>;
  if (widget.kind === "gauge") {
    const ratio = Math.min(1, Math.max(0, data.value / Math.max(widget.target, 0.01)));
    return <div className="sim-gauge">
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="60" r="48" fill="none" stroke="var(--color-border-subtle)" strokeWidth="9" />
        <circle cx="60" cy="60" r="48" fill="none" stroke={color} strokeWidth="9" strokeLinecap="round" strokeDasharray={`${ratio * 302} 302`} transform="rotate(-90 60 60)" />
      </svg>
      <div><strong>{format(data.value)}</strong><span>{t("simulation.studio.target", { value: format(widget.target) })}</span></div>
      <progress className="sr-only" max={widget.target} value={Math.min(data.value, widget.target)} aria-label={t("simulation.studio.target", { value: format(widget.target) })} />
    </div>;
  }

  const table = <div className="sim-data-table"><table>
    <caption className="sr-only">{widget.title || t(`simulation.studio.metric.${widget.metric}`)}</caption>
    <thead><tr><th scope="col">{t(data.categorical ? "simulation.studio.category" : "simulation.studio.simulatedTime")}</th><th scope="col">{t("simulation.studio.value")}</th></tr></thead>
    <tbody>{points.map((point, index) => <tr key={`${point.label}-${index}`}><th scope="row">{point.label}</th><td>{format(point.value)}</td></tr>)}</tbody>
  </table></div>;
  if (widget.kind === "table") return table;

  const axes = <>
    <CartesianGrid stroke="var(--sim-chart-grid)" vertical={false} />
    <XAxis dataKey="label" tick={{ fill: "var(--color-text-muted)", fontSize: 11 }} tickLine={false} axisLine={false} hide={!widget.showLabels} minTickGap={24} />
    <YAxis domain={[0, (max: number) => Math.max(1, max)]} tick={{ fill: "var(--color-text-muted)", fontSize: 11 }} tickLine={false} axisLine={false} width={52} tickFormatter={(value: number) => data.unit === "currency" ? new Intl.NumberFormat(lang, { notation: "compact" }).format(value) : format(value)} hide={!widget.showLabels} />
    <Tooltip formatter={(value) => [format(typeof value === "number" ? value : null), t("simulation.studio.value")]} contentStyle={{ background: "var(--card)", borderColor: "var(--border)", borderRadius: 8, fontSize: 12 }} />
  </>;
  const chartProps = { data: points, accessibilityLayer: false, margin: { top: 12, right: 12, bottom: 0, left: 0 } };
  let chart: React.ReactElement;
  if (widget.kind === "radial") {
    const radialPoints = points.map((point, index) => ({ ...point, fill: COLORS[index % COLORS.length] }));
    chart = <RadialBarChart data={radialPoints} accessibilityLayer={false} innerRadius="20%" outerRadius="90%" startAngle={90} endAngle={-270}>
      <RadialBar dataKey="value" background isAnimationActive={false} /><Tooltip formatter={(value) => format(typeof value === "number" ? value : null)} />
    </RadialBarChart>;
  } else if (widget.kind === "pie" || widget.kind === "donut") {
    chart = <PieChart accessibilityLayer={false}><Pie data={points.filter((point) => point.value > 0)} dataKey="value" nameKey="label" innerRadius={widget.kind === "donut" ? "55%" : 0} outerRadius="85%" isAnimationActive={false}>
      {points.filter((point) => point.value > 0).map((point, index) => <Cell key={`${point.label}-${index}`} fill={COLORS[index % COLORS.length]} />)}
    </Pie><Tooltip formatter={(value) => format(typeof value === "number" ? value : null)} /></PieChart>;
  } else if (widget.kind === "bar") {
    chart = <BarChart {...chartProps} layout="vertical" margin={{ left: 0, right: 16, top: 12 }}>
      <CartesianGrid stroke="var(--sim-chart-grid)" horizontal={false} /><XAxis type="number" hide />
      <YAxis type="category" dataKey="label" width={110} tick={{ fill: "var(--foreground)", fontSize: 11 }} tickLine={false} axisLine={false} hide={!widget.showLabels} />
      <Tooltip formatter={(value) => format(typeof value === "number" ? value : null)} /><Bar dataKey="value" fill={color} radius={[0, 4, 4, 0]} isAnimationActive={false} maxBarSize={22} />
    </BarChart>;
  } else if (widget.kind === "column") chart = <BarChart {...chartProps}>{axes}<Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} isAnimationActive={false} maxBarSize={36} /></BarChart>;
  else if (widget.kind === "area") chart = <AreaChart {...chartProps}>{axes}<Area dataKey="value" type="stepAfter" fill={color} fillOpacity={0.12} stroke={color} strokeWidth={2} isAnimationActive={false} /></AreaChart>;
  else chart = <LineChart {...chartProps}>{axes}<Line dataKey="value" type="stepAfter" stroke={color} strokeWidth={2} dot={points.length === 1} isAnimationActive={false} /></LineChart>;

  return <>
    <div className="sim-widget-chart" aria-hidden="true"><ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer></div>
    <details className="sim-widget-data"><summary>{t("simulation.studio.viewData")}</summary>{table}</details>
  </>;
}

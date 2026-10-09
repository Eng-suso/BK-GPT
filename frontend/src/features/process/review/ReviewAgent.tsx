import React from "react";
import { ArrowUp, ArrowUpRight, BookOpen, ChevronDown, FlaskConical, Grip, Square, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";
import { Surface } from "@/ui/surface";
import { Textarea } from "@/ui/textarea";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/ui/dropdown-menu";
import { CanvasResizeHandle } from "@/components/layout/CanvasWorkspace";
import { InlineNotice } from "@/components/feedback/InlineNotice";
import { useChatSessions } from "@/features/chat/hooks/useChatSessions";
import { useChatStream } from "@/features/chat/hooks/useChatStream";
import { renderMarkdown } from "@/features/chat/lib/markdown";
import type { ChatScope } from "@/contracts/chat";
import { ReviewMascot } from "./ReviewMascot";
import type { ReviewNode, ReviewActionKind } from "./reviewModel";

const STARTERS = ["understand", "opinion", "alternatives"] as const;
const CAPABILITIES = ["evidence", "handoffs", "controls", "automation", "questions", "simulation", "asIs", "toBe"] as const;

export function ReviewAgent({ node, projectId, processId, processName, bpmnModelId, revision, anchor, request, onDetails, onPropose, onSimulation, onChooseTask }: {
  node: ReviewNode | null; projectId: string; processId: string; processName: string; bpmnModelId: string;
  revision: string; anchor: { left: number; top: number } | null;
  request: { id: number; prompt: string } | null; onDetails: () => void; onPropose: (kind: ReviewActionKind, detail: string, returnTarget: HTMLButtonElement | null) => void; onSimulation: () => void; onChooseTask: () => void;
}) {
  const { t } = useTranslation("process");
  const [open, setOpen] = React.useState(false);
  const [drafts, setDrafts] = React.useState<Record<string, string>>({});
  const chatId = React.useId();
  const [openedRequest, setOpenedRequest] = React.useState<number | null>(null);
  if (request && request.id !== openedRequest) {
    setOpenedRequest(request.id); setOpen(true);
    if (node && request.prompt) setDrafts(previous => ({ ...previous, [node.id]: request.prompt }));
  }
  const panel = React.useRef<HTMLDivElement>(null);
  const [available, setAvailable] = React.useState({ width: 392, height: 560 });
  const [size, setSize] = React.useState<{ width: number; height: number } | null>(null);
  const gesture = React.useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  React.useLayoutEffect(() => {
    const stage = panel.current?.parentElement;
    if (!stage) return;
    const observer = new ResizeObserver(() => { const style = getComputedStyle(panel.current!); const edge = Number.parseFloat(style.right) || 16; const bottom = Number.parseFloat(style.bottom) || 64; setAvailable({ width: Math.max(1, stage.clientWidth - edge * 2), height: Math.max(1, stage.clientHeight - edge - bottom) }); });
    observer.observe(stage); return () => observer.disconnect();
  }, []);
  const clamp = (next: { width: number; height: number }) => ({ width: Math.max(Math.min(280, available.width), Math.min(available.width, next.width)), height: Math.max(Math.min(320, available.height), Math.min(available.height, next.height)) });
  const current = size ? clamp(size) : { width: Math.min(392, available.width), height: Math.min(560, available.height) };
  const trigger = React.useRef<HTMLButtonElement>(null);
  const launcher = React.useRef<HTMLDivElement>(null);
  const [position, setPosition] = React.useState<{ left: number; top: number } | null>(null);
  const [stageSize, setStageSize] = React.useState({ width: 1, height: 1, avatarWidth: 196, avatarHeight: 64 });
  const moveGesture = React.useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  React.useLayoutEffect(() => {
    const stage = launcher.current?.parentElement;
    if (!stage) return;
    const measure = () => setStageSize(previous => ({ width: stage.clientWidth, height: stage.clientHeight, avatarWidth: launcher.current?.offsetWidth || previous.avatarWidth, avatarHeight: launcher.current?.offsetHeight || previous.avatarHeight }));
    measure(); const observer = new ResizeObserver(measure); observer.observe(stage); if (launcher.current) observer.observe(launcher.current);
    return () => observer.disconnect();
  }, []);
  const clampPosition = (next: { left: number; top: number }) => ({
    left: Math.max(8, Math.min(Math.max(8, stageSize.width - stageSize.avatarWidth - 8), next.left)),
    top: Math.max(8, Math.min(Math.max(8, stageSize.height - stageSize.avatarHeight - 44), next.top)),
  });
  const placed = position || anchor;
  const close = () => { setOpen(false); requestAnimationFrame(() => trigger.current?.focus({ preventScroll: true })); };
  return <>
    <div ref={launcher} className="review-agent-position" hidden={open} style={placed ? { left: `clamp(8px, ${placed.left}px, max(8px, calc(100% - ${stageSize.avatarWidth}px - 8px)))`, top: `clamp(8px, ${placed.top}px, max(8px, calc(100% - ${stageSize.avatarHeight}px - 44px)))`, right: "auto", bottom: "auto" } : undefined}>
    <Surface asChild variant="floating"><Button ref={trigger} variant="ghost" className="review-agent-launcher" aria-label={t("review.agent.open")} aria-expanded={open} aria-controls={chatId} onClick={() => setOpen(true)}>
      <span key={node?.id ?? "process"} className="review-mascot-orbit"><ReviewMascot /></span>
      <span className="review-agent-launcher-copy"><b>DeliR</b><span>{node?.name ?? t("review.agent.invite")}</span></span>
    </Button></Surface>
    <Button variant="ghost" size="icon-sm" className="review-agent-move" aria-label={t("review.agent.move")} title={t("review.agent.moveHint")} onPointerDown={event => {
      if (event.button !== 0 || !launcher.current) return;
      moveGesture.current = { x: event.clientX, y: event.clientY, left: launcher.current.offsetLeft, top: launcher.current.offsetTop };
      event.preventDefault(); event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId);
    }} onPointerMove={event => { const start = moveGesture.current; if (start) setPosition(clampPosition({ left: start.left + event.clientX - start.x, top: start.top + event.clientY - start.y })); }} onPointerUp={event => { moveGesture.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }} onPointerCancel={() => { moveGesture.current = null; }} onLostPointerCapture={() => { moveGesture.current = null; }} onKeyDown={event => {
      const steps: Record<string, [number, number]> = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] };
      const step = steps[event.key]; if (step && launcher.current) { event.preventDefault(); event.stopPropagation(); setPosition(clampPosition({ left: launcher.current.offsetLeft + step[0], top: launcher.current.offsetTop + step[1] })); }
      if (event.key === "Home") { event.preventDefault(); setPosition(null); }
    }}><Grip aria-hidden /></Button>
    </div>
    <Surface ref={panel} variant="floating" id={chatId} style={size ? { width: current.width, height: current.height } : undefined} className="review-agent-chat" role="dialog" aria-label={t("review.agent.title")} hidden={!open} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); close(); } }}>
      <CanvasResizeHandle label={t("review.agent.resize")} hint={t("review.agent.resizeHint")} className="review-chat-resize" aria-description={`${Math.round(current.width)} × ${Math.round(current.height)} px`} onPointerDown={event => {
        if (event.button !== 0 || !panel.current) return;
        const rect = panel.current.getBoundingClientRect(); gesture.current = { x: event.clientX, y: event.clientY, width: rect.width, height: rect.height };
        event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
      }} onPointerMove={event => { const start = gesture.current; if (start) setSize(clamp({ width: start.width + start.x - event.clientX, height: start.height + start.y - event.clientY })); }} onPointerUp={() => { gesture.current = null; }} onPointerCancel={() => { gesture.current = null; }} onKeyDown={event => {
        const steps: Record<string, [number, number]> = { ArrowLeft: [20, 0], ArrowRight: [-20, 0], ArrowUp: [0, 20], ArrowDown: [0, -20] };
        const step = steps[event.key]; if (step) { event.preventDefault(); setSize(clamp({ width: current.width + step[0], height: current.height + step[1] })); }
        if (event.key === "Home") { event.preventDefault(); setSize(null); }
      }} />
      <header className="review-chat-header"><ReviewMascot /><div className="review-chat-heading"><span>DeliR <span className="text-muted-foreground">/ Review</span></span><h3>{node?.name ?? t("review.agent.chooseTitle")}</h3></div><div className="flex shrink-0 gap-1">{node && <Button variant="ghost" size="icon-sm" aria-label={t("review.agent.details")} onClick={onDetails}><BookOpen aria-hidden /></Button>}<Button variant="ghost" size="icon-sm" aria-label={t("review.agent.close")} onClick={close}><X aria-hidden /></Button></div></header>
      {node ? <TaskReviewConversation key={node.id} node={node} open={open} scope={{ type: "canvas", projectId, processId, processName, bpmnModelId, reviewNodeId: node.id, reviewBaseRevision: revision }} draft={drafts[node.id] ?? ""} onDraft={value => setDrafts(previous => ({ ...previous, [node.id]: value }))} onPropose={onPropose} onSimulation={onSimulation} /> : <div className="review-chat-empty"><ReviewMascot /><h4>{t("review.agent.chooseTitle")}</h4><p>{t("review.agent.chooseDescription")}</p><Button size="sm" variant="outline" onClick={onChooseTask}>{t("review.agent.chooseTask")}</Button></div>}
    </Surface>
  </>;
}

function TaskReviewConversation({ node, scope, open, draft, onDraft, onPropose, onSimulation }: {
  node: ReviewNode; scope: ChatScope; open: boolean; draft: string;
  onDraft: (value: string) => void; onPropose: (kind: ReviewActionKind, detail: string, returnTarget: HTMLButtonElement | null) => void; onSimulation: () => void;
}) {
  const { t } = useTranslation("process");
  const sessions = useChatSessions(scope, "gpt-5.6-luna");
  const stream = useChatStream({ scope, selectedModel: "gpt-5.6-luna", choices: { posture: "review", autonomy: "manual", reasoning: "medium" }, activeSession: sessions.activeSession, currentThreadId: sessions.currentThreadId, ensureThread: sessions.ensureThread, selectThread: sessions.selectThread, commitTranscript: sessions.commitTranscript });
  const messages = stream.liveThreadId && stream.liveThreadId === sessions.currentThreadId ? stream.liveMessages ?? [] : sessions.activeSession?.messages ?? [];
  const proposalTrigger = React.useRef<HTMLButtonElement | null>(null);
  const input = React.useRef<HTMLTextAreaElement>(null);
  const list = React.useRef<HTMLDivElement>(null);
  const pinned = React.useRef(true);
  const lastMessage = messages[messages.length - 1];
  React.useEffect(() => { if (open) input.current?.focus({ preventScroll: true }); }, [open]);
  React.useEffect(() => { pinned.current = true; }, [node.id]);
  React.useLayoutEffect(() => { if (pinned.current && list.current) list.current.scrollTop = list.current.scrollHeight; }, [lastMessage?.content, messages.length, stream.isBusy]);
  const send = (text: string) => {
    if (!text.trim() || stream.isBusy) return;
    stream.clearStreamError();
    void stream.sendMessage(text.trim());
  };
  return <>
    <div className="review-chat-context"><span className="review-chat-context-dot" aria-hidden />{t("review.agent.contextBound")}<Button size="sm" variant="ghost" onClick={onSimulation}><FlaskConical aria-hidden />{t("review.agent.simulation")}</Button></div>
    <div ref={list} className="review-chat-transcript ui-scrollbar" role="log" aria-label={t("review.agent.conversation")} aria-live="off" tabIndex={0} onScroll={() => { const element = list.current; if (element) pinned.current = element.scrollHeight - element.scrollTop - element.clientHeight < 48; }}>
      {!messages.length && <div className="review-chat-welcome"><p>{t("review.agent.welcome", { name: node.name })}</p><p>{t("review.agent.welcomeDetail")}</p><div className="review-chat-starters">{STARTERS.map(key => <Button key={key} size="sm" variant="outline" disabled={stream.isBusy} onClick={() => send(t(`review.agent.prompt.${key}`))}>{t(`review.agent.shortcut.${key}`)}<ArrowUpRight aria-hidden /></Button>)}</div></div>}
      {messages.filter(message => message.role !== "system").map((message, index) => <article key={message.id || `${message.role}:${index}`} className={`review-chat-message review-chat-message--${message.role}`} aria-label={t(message.role === "user" ? "review.agent.you" : "review.agent.assistant")}>
        {message.role === "user" ? <p>{message.content}</p> : message.role === "error" ? <p>{message.content}</p> : <><div className="review-chat-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }} />{message.content && !stream.isBusy && !message.stoppedByUser && <DropdownMenu><DropdownMenuTrigger asChild><Button size="sm" variant="ghost" className="review-chat-save" onPointerDownCapture={event => { proposalTrigger.current = event.currentTarget; }} onKeyDownCapture={event => { proposalTrigger.current = event.currentTarget; }}>{t("review.agent.saveHypothesis")}<ChevronDown aria-hidden /></Button></DropdownMenuTrigger><DropdownMenuContent align="start"><DropdownMenuItem onSelect={() => onPropose("as_is_proposal", message.content, proposalTrigger.current)}>{t("review.agent.asIs")}</DropdownMenuItem><DropdownMenuItem onSelect={() => onPropose("candidate", message.content, proposalTrigger.current)}>{t("review.agent.toBe")}</DropdownMenuItem></DropdownMenuContent></DropdownMenu>}</>}
      </article>)}
      {stream.isBusy && <p role="status" className="review-chat-progress">{t("review.agent.thinking")}</p>}
    </div>
    {!stream.isBusy && lastMessage?.role === "assistant" && <span role="status" className="sr-only">{t("review.agent.answerReady")}</span>}
    {stream.streamError && <InlineNotice className="mx-3" tone="error" title={t("review.agent.error")} action={<Button size="sm" variant="outline" onClick={() => send(stream.lastUserPrompt)}>{t("review.retry")}</Button>}>{stream.streamError}</InlineNotice>}
    {sessions.isOffline && <InlineNotice className="mx-3" tone="warning" title={t("review.agent.historyError")} action={<Button size="sm" variant="outline" onClick={sessions.retrySessions}>{t("review.retry")}</Button>} />}
    <form className="review-chat-composer" onSubmit={event => { event.preventDefault(); if (!draft.trim() || stream.isBusy) return; send(draft); onDraft(""); }}>
      <div className="review-chat-composer-top"><DropdownMenu><DropdownMenuTrigger asChild><Button size="sm" variant="ghost" disabled={stream.isBusy}>{t("review.agent.explore")}<ChevronDown aria-hidden /></Button></DropdownMenuTrigger><DropdownMenuContent align="start">{CAPABILITIES.map(key => <DropdownMenuItem key={key} onSelect={() => send(t(`review.agent.prompt.${key}`))}>{t(`review.agent.shortcut.${key}`)}</DropdownMenuItem>)}</DropdownMenuContent></DropdownMenu><span>{t("review.agent.enterHint")}</span></div>
      <Surface variant="inset" className="review-chat-input"><Textarea ref={input} value={draft} onChange={event => onDraft(event.target.value)} aria-label={t("review.agent.input")} placeholder={t("review.agent.placeholder")} maxLength={4000} rows={2} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} />{stream.isBusy ? <Button type="button" size="icon" variant="outline" aria-label={t("review.agent.stop")} onClick={stream.stopStreaming}><Square aria-hidden className="size-3" /></Button> : <Button type="submit" size="icon" disabled={!draft.trim()} aria-label={t("review.agent.send")}><ArrowUp aria-hidden /></Button>}</Surface>
    </form>
  </>;
}

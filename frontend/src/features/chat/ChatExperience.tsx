import React, { useCallback, useEffect, useRef, useState } from "react";
import { chatScopeKey, toApiChatScope } from "../../contracts/chat";
import { API_BASE } from "../../lib/api";
import { withAdminAuth, withAuth } from "../../lib/security";
import { notifyWorkspaceChanged } from "../../lib/workspaceEvents";
import type { AgentActivity, ChatMessage, ChatSession } from "./types";
import type { NavigationTab } from "./navigationTypes";
import type { ChatScope } from "./chatScope";
import { titleForScope } from "./chatScope";
import { ChatShell } from "./ChatShell";

function sessionTitle(message: string): string {
  const clean = message.trim().replace(/\s+/g, " ");
  return clean.length > 28 ? `${clean.slice(0, 28)}...` : clean || "Nuova chat";
}

function notifyChatWorkspaceChanged(scope: ChatScope) {
  if (scope.type !== "canvas") {
    notifyWorkspaceChanged();
    return;
  }

  notifyWorkspaceChanged({
    bpmnModelId: scope.bpmnModelId,
    forceCanvasReload: true,
  });
}

const AGENT_ACTIVITY_LABELS: Record<string, string> = {
  canvas_subgraph: "Apro il contesto canvas",
  canvas_router: "Scelgo il percorso operativo",
  canvas_macro_agent: "Coordino il lavoro sul canvas",
  patch_edit_subgraph: "Eseguo la modifica locale",
  canvas_patch_edit_agent: "Aggiorno gli elementi del canvas",
  construction_subgraph: "Preparo la costruzione del canvas",
  canvas_construction_agent: "Genero o revisiono il modello",
  layout_subgraph: "Preparo il disegno del canvas",
  canvas_drawing_agent: "Ridisegno elementi e collegamenti",
  validation_subgraph: "Verifico il canvas",
  canvas_validation_agent: "Controllo struttura e copertura",
  evaluate_canvas_completion: "Valuto se la richiesta e' completa",
  canvas_completion_report: "Chiudo con il risultato verificato",
  ask_canvas_clarification: "Preparo una domanda di chiarimento",
};

function activityLabelForNode(nodeName: string) {
  return AGENT_ACTIVITY_LABELS[nodeName] || nodeName.replace(/_/g, " ");
}

function nextAgentActivity(
  current: AgentActivity[] | undefined,
  nodeName: string
): AgentActivity[] {
  const existing = current || [];
  const completed = existing.map((item) =>
    item.status === "running" ? { ...item, status: "completed" as const } : item
  );
  const previousIndex = completed.findIndex((item) => item.key === nodeName);
  const nextItem: AgentActivity = {
    key: nodeName,
    label: activityLabelForNode(nodeName),
    status: "running",
  };

  if (previousIndex >= 0) {
    const updated = [...completed];
    updated[previousIndex] = nextItem;
    return updated;
  }

  return [...completed, nextItem];
}

function completeAgentActivity(current: AgentActivity[] | undefined): AgentActivity[] | undefined {
  if (!current || current.length === 0) return current;
  return current.map((item) => ({ ...item, status: "completed" }));
}

type RawMessage = {
  id?: string | number;
  role?: string;
  content?: string;
  created_at?: string;
  createdAt?: string;
};

type RawSession = {
  thread_id?: string;
  threadId?: string;
  title?: string;
  model_name?: string;
  modelName?: string;
  created_at?: string;
  createdAt?: string;
  updated_at?: string;
  updatedAt?: string;
  message_count?: number;
  messages?: RawMessage[];
};

function normalizeSession(session: RawSession): ChatSession {
  return {
    threadId: session.thread_id || session.threadId || "",
    title: session.title || "Nuova chat",
    modelName: session.model_name || session.modelName || null,
    createdAt: session.created_at || session.createdAt || "",
    updatedAt: session.updated_at || session.updatedAt || "",
    messageCount: session.message_count || (session.messages ? session.messages.length : 0),
    messages: (session.messages || []).map((m) => ({
      id: String(m.id || ""),
      role: (m.role as ChatMessage["role"]) || "user",
      content: m.content || "",
      createdAt: m.created_at || m.createdAt,
    })),
  };
}

type ChatExperienceProps = {
  chrome?: "full" | "panel";
  layout?: "standalone" | "embedded";
  scope?: ChatScope;
};

type ApiConnectionState = {
  status: "checking" | "connected" | "offline";
  message: string | null;
};

type BpmnReview = {
  bpmn_model_id: string;
  process_id: string;
  source_text: string;
  process_understanding?: ProcessUnderstandingSummary;
  bpmn_semantic_model?: BpmnSemanticModelSummary;
  quality_report?: ProcessQualityReportSummary;
  bpmn_brief: string;
  readiness_score: number;
  missing_information: string[];
  created_at: string;
  updated_at: string;
};

type ProcessUnderstandingSummary = {
  actors?: Array<{ id: string; label: string; kind: string }>;
  decisions?: Array<{ id: string; label: string; outcomes?: string[] }>;
  exceptions?: Array<{ id: string; label: string; handling?: string | null; is_defined?: boolean }>;
  data_objects?: Array<{ id: string; label: string; kind: string }>;
  handoffs?: Array<{ id: string; artifact?: string | null; trigger?: string | null }>;
  alternative_paths?: Array<{ id: string; label: string; is_confirmed?: boolean }>;
  unknowns?: Array<{ question: string; severity: string }>;
};

type ProcessQualityReportSummary = {
  overall_score?: number;
  approval_recommendation?: string;
  dimension_scores?: Array<{ dimension: string; score: number; findings?: string[]; blocking?: boolean }>;
  blocking_issues?: Array<{ id: string; message: string; recommendation?: string | null }>;
  warnings?: Array<{ id: string; message: string; recommendation?: string | null }>;
  improvement_actions?: Array<{ id: string; target_field: string; action: string; priority?: string }>;
};

type BpmnSemanticModelSummary = {
  lanes?: Array<{ id: string; name: string; flowNodeRefs?: string[] }>;
  flowNodes?: Array<{ id: string; type: string; name: string; laneId?: string | null }>;
  sequenceFlows?: Array<{ id: string; sourceRef: string; targetRef: string; name?: string | null }>;
  model_warnings?: string[];
};

export const ChatExperience: React.FC<ChatExperienceProps> = ({
  chrome = "full",
  layout = "standalone",
  scope = { type: "consultant" },
}) => {
  const apiScope = toApiChatScope(scope);
  const persistentApiScope = toApiChatScope(scope, { includeTransient: false });
  const scopeKey = chatScopeKey(apiScope);
  const [activeTab, setActiveTab] = useState<NavigationTab>("chat");
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const currentThreadIdRef = useRef<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [selectedModel, setSelectedModel] = useState("gpt-5.6-luna");
  const [lastUserPrompt, setLastUserPrompt] = useState("");
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [bpmnReview, setBpmnReview] = useState<BpmnReview | null>(null);
  const [isApprovingReview, setIsApprovingReview] = useState(false);
  const [apiConnection, setApiConnection] = useState<ApiConnectionState>({
    status: "checking",
    message: null,
  });
  const loadSessionsRetryRef = useRef<number | null>(null);

  const activeSession = sessions.find((s) => s.threadId === currentThreadId) || null;
  const messages = activeSession ? activeSession.messages : [];
  const activeTitle = activeSession ? activeSession.title : titleForScope(scope);

  // Keep the ref in sync with state so callbacks can read the latest value without being dependencies.
  useEffect(() => {
    currentThreadIdRef.current = currentThreadId;
  }, [currentThreadId]);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 2800);
  };

  const clearLoadSessionsRetry = () => {
    if (loadSessionsRetryRef.current !== null) {
      window.clearTimeout(loadSessionsRetryRef.current);
      loadSessionsRetryRef.current = null;
    }
  };

  const upsertSession = (rawSession: RawSession): ChatSession => {
    const normalized = normalizeSession(rawSession);
    setSessions((prev) => {
      const idx = prev.findIndex((s) => s.threadId === normalized.threadId);
      let updated: ChatSession[];
      if (idx >= 0) {
        updated = [...prev];
        updated[idx] = { ...updated[idx], ...normalized };
      } else {
        updated = [normalized, ...prev];
      }
      return updated.sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
    });
    return normalized;
  };

  const loadSessionDetail = useCallback(async (threadId: string) => {
    try {
      const res = await fetch(
        `${API_BASE}/v1/consultant-chat/sessions/${threadId}`,
        withAuth(),
      );
      if (!res.ok) return;
      const data = await res.json();
      upsertSession(data);
    } catch (err) {
      console.error(err);
    }
  }, []);

  const loadSessions = useCallback(async () => {
    clearLoadSessionsRetry();

    for (let attempt = 0; attempt <= 20; attempt += 1) {
      try {
        const params = new URLSearchParams({ scope_key: scopeKey });
        const res = await fetch(
          `${API_BASE}/v1/consultant-chat/sessions?${params}`,
          withAuth(),
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const list: ChatSession[] = data.map(normalizeSession);
        clearLoadSessionsRetry();
        setApiConnection({ status: "connected", message: null });
        setSessions(list);
        // Use ref instead of state to avoid making currentThreadId a dependency,
        // which would cause an infinite loop: loadSessions mutates currentThreadId
        // -> new useCallback ref -> useEffect re-fires -> loadSessions again.
        if (list.length > 0 && !currentThreadIdRef.current) {
          setCurrentThreadId(list[0].threadId);
          loadSessionDetail(list[0].threadId);
        }
        return;
      } catch (err) {
        console.error(err);
        setApiConnection({
          status: "offline",
          message: `Backend non raggiungibile su ${API_BASE || "origine corrente"}. Riprovo a caricare la cronologia...`,
        });

        if (attempt === 20) return;

        await new Promise<void>((resolve) => {
          loadSessionsRetryRef.current = window.setTimeout(
            resolve,
            Math.min(1000 + attempt * 250, 4000)
          );
        });
      }
    }
  }, [scopeKey, loadSessionDetail]);

  // Extract stable primitives from scope to avoid unstable object references in useCallback deps.
  // scope defaults to `{ type: "consultant" }` — a new object on every render, which would cause
  // loadBpmnReview to be recreated each render and re-trigger the useEffect indefinitely.
  const scopeType = scope.type;
  const bpmnModelIdForReview = scope.type === "canvas" ? scope.bpmnModelId : null;

  const loadBpmnReview = useCallback(async () => {
    if (scopeType !== "canvas" || !bpmnModelIdForReview) {
      setBpmnReview(null);
      return;
    }

    try {
      const res = await fetch(
        `${API_BASE}/v1/workspace/bpmn-models/${bpmnModelIdForReview}/review`,
        withAuth({ cache: "no-store" }),
      );

      if (!res.ok) {
        setBpmnReview(null);
        return;
      }

      setBpmnReview(await res.json());
    } catch (err) {
      console.error(err);
      setBpmnReview(null);
    }
  }, [scopeType, bpmnModelIdForReview]);

  useEffect(() => {
    let isMounted = true;

    async function init() {
      await Promise.resolve();
      if (!isMounted) return;

      setSessions([]);
      setCurrentThreadId(null);
      currentThreadIdRef.current = null;
      setBpmnReview(null);

      void loadSessions();
      void loadBpmnReview();
    }

    void init();

    return () => {
      isMounted = false;
      clearLoadSessionsRetry();
    };
  }, [scopeKey, loadSessions, loadBpmnReview]);

  const createBackendSession = async () => {
    const res = await fetch(`${API_BASE}/v1/consultant-chat/sessions`, withAuth({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_name: selectedModel, scope: persistentApiScope }),
    }));
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(body?.detail || "Impossibile creare la sessione");
    }
    return res.json();
  };

  const transcribeAudio = async (file: File): Promise<string> => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("language", "it");

    const res = await fetch(`${API_BASE}/v1/audio/transcriptions`, withAuth({
      method: "POST",
      body: formData,
    }));

    if (!res.ok) {
      const errorBody = await res.json().catch(() => null);
      throw new Error(errorBody?.detail || "Trascrizione audio fallita");
    }

    const data = await res.json();
    return String(data.text || "").trim();
  };

  const ensureSession = async (firstMessage = ""): Promise<ChatSession> => {
    if (activeSession) return activeSession;
    const data = await createBackendSession();
    const session = upsertSession({ ...data, title: sessionTitle(firstMessage), messages: [] });
    setCurrentThreadId(session.threadId);
    return session;
  };

  const appendVisibleSendError = (session: ChatSession | null, content: string, message: string) => {
    const errorMessage: ChatMessage = { role: "error", content: message };

    if (session) {
      setSessions((prev) =>
        prev.map((s) => {
          if (s.threadId !== session.threadId) return s;
          const msgs = s.messages.at(-1)?.content === "Sto elaborando..." ? s.messages.slice(0, -1) : s.messages;
          return { ...s, messages: [...msgs, errorMessage] };
        })
      );
      return;
    }

    const fallbackThreadId = `local-error-${Date.now()}`;
    setCurrentThreadId(fallbackThreadId);
    setSessions((prev) => [
      {
        threadId: fallbackThreadId,
        title: sessionTitle(content),
        modelName: selectedModel,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messageCount: 2,
        messages: [
          { role: "user", content },
          errorMessage,
        ],
      },
      ...prev,
    ]);
  };

  const sendMessage = async (content: string) => {
    setLastUserPrompt(content);
    let session: ChatSession | null = null;

    const userMessage: ChatMessage = { role: "user", content };
    const loadingMessage: ChatMessage = { role: "assistant", content: "Sto elaborando...", activity: [] };

    setIsBusy(true);

    try {
      session = await ensureSession(content);
      const sendSession = session;

      setSessions((prev) =>
        prev.map((s) => {
          if (s.threadId !== sendSession.threadId) return s;
          const cleanMsgs = s.messages.filter((m) => m.role !== "error");
          return {
            ...s,
            title: s.title === "Nuova chat" ? sessionTitle(content) : s.title,
            messages: [...cleanMsgs, userMessage, loadingMessage],
          };
        })
      );

      const res = await fetch(
        `${API_BASE}/v1/consultant-chat/sessions/${sendSession.threadId}/messages/stream`,
        withAuth({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: content,
            model_name: selectedModel,
            scope: apiScope,
          }),
        }),
      );

      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Streaming fallito");
      }

      setApiConnection({ status: "connected", message: null });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulatedText = "";
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);

          if (event.type === "node" && event.node) {
            setSessions((prev) =>
              prev.map((s) => {
                if (s.threadId !== sendSession.threadId) return s;
                const msgs = [...s.messages];
                const last = msgs[msgs.length - 1];
                if (!last || last.role !== "assistant") return s;
                msgs[msgs.length - 1] = {
                  ...last,
                  activity: nextAgentActivity(last.activity, String(event.node)),
                };
                return { ...s, messages: msgs };
              })
            );
          }

          if (event.type === "delta") {
            accumulatedText += event.content || "";
            setSessions((prev) =>
              prev.map((s) => {
                if (s.threadId !== sendSession.threadId) return s;
                const msgs = [...s.messages];
                const last = msgs[msgs.length - 1];
                msgs[msgs.length - 1] = {
                  ...(last || { role: "assistant" as const }),
                  role: "assistant",
                  content: accumulatedText,
                };
                return { ...s, messages: msgs };
              })
            );
          }

          if (event.type === "done") {
            accumulatedText = event.message || accumulatedText;
            if (accumulatedText) {
              setSessions((prev) =>
                prev.map((s) => {
                  if (s.threadId !== sendSession.threadId) return s;
                  const msgs = [...s.messages];
                  const last = msgs[msgs.length - 1];
                  msgs[msgs.length - 1] = {
                    ...(last || { role: "assistant" as const }),
                    role: "assistant",
                    content: accumulatedText,
                    activity: completeAgentActivity(last?.activity),
                  };
                  return { ...s, messages: msgs };
                })
              );
            }
          }

          if (event.type === "error") {
            throw new Error(
              event.error?.message ||
                event.error?.detail ||
                event.detail ||
                "Errore backend"
            );
          }
        }
      }

      await loadSessionDetail(sendSession.threadId);
      await loadBpmnReview();
      notifyChatWorkspaceChanged(scope);
    } catch (err) {
      console.error(err);
      const detail = err instanceof Error ? err.message : "Errore sconosciuto";
      setApiConnection({
        status: "offline",
        message: `Backend non raggiungibile o richiesta fallita: ${detail}`,
      });
      appendVisibleSendError(
        session,
        content,
        `Non sono riuscito a completare questa richiesta. ${detail}`
      );
    } finally {
      setIsBusy(false);
    }
  };

  const approveBpmnReview = async () => {
    if (scope.type !== "canvas" || !bpmnReview) return;

    setIsApprovingReview(true);

    try {
      const res = await fetch(
        `${API_BASE}/v1/workspace/bpmn-models/${scope.bpmnModelId}/review/approve`,
        withAuth({ method: "POST" }),
      );

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Nessuna review BPMN pendente da approvare.");
      }

      setBpmnReview(null);
      notifyWorkspaceChanged({ bpmnModelId: scope.bpmnModelId, forceCanvasReload: true });
      showToast("BPMN generato e salvato.");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Approvazione BPMN non riuscita.");
    } finally {
      setIsApprovingReview(false);
    }
  };

  return (
    <>
      <ChatShell
        chrome={chrome}
        layout={layout}
        activeTab={activeTab}
        sessions={sessions}
        currentThreadId={currentThreadId}
        messages={messages}
        activeTitle={activeTitle}
        isBusy={isBusy}
        selectedModel={selectedModel}
        onTabChange={setActiveTab}
        onThemeToggle={() => showToast("Tema attivo.")}
        onNewChat={() => setCurrentThreadId(null)}
        onSelectSession={(id) => {
          setCurrentThreadId(id);
          loadSessionDetail(id);
        }}
        onDeleteSession={async (id) => {
          try {
            await fetch(
              `${API_BASE}/v1/consultant-chat/sessions/${id}`,
              withAdminAuth({ method: "DELETE" }),
            );
          } catch (e) {
            console.error(e);
          }
          setSessions((prev) => prev.filter((s) => s.threadId !== id));
          if (currentThreadId === id) setCurrentThreadId(null);
          showToast("Conversazione eliminata.");
        }}
        onClearHistory={async () => {
          try {
            const params = new URLSearchParams({ scope_key: scopeKey });
            await fetch(
              `${API_BASE}/v1/consultant-chat/sessions?${params}`,
              withAdminAuth({ method: "DELETE" }),
            );
          } catch (e) {
            console.error(e);
          }
          setSessions([]);
          setCurrentThreadId(null);
          showToast("Cronologia eliminata.");
        }}
        onSearch={() => showToast("Ricerca cronologia.")}
        onConfig={() => showToast(`API backend: ${API_BASE || "locale"}`)}
        onShare={async () => {
          const text = messages.map((m) => `${m.role}: ${m.content}`).join("\n\n");
          await navigator.clipboard?.writeText(text);
          showToast("Conversazione copiata.");
        }}
        onSelectPrompt={sendMessage}
        onSendMessage={sendMessage}
        onTranscribeAudio={transcribeAudio}
        onRetry={() => lastUserPrompt && sendMessage(lastUserPrompt)}
        onAttach={() => showToast("Carica un file audio da trascrivere.")}
        onVoice={() => showToast("Registrazione vocale pronta.")}
        onModelChange={setSelectedModel}
        reviewSlot={
          <>
            {apiConnection.status === "offline" && apiConnection.message ? (
              <section className="api-status-card" role="status">
                <strong>Backend scollegato</strong>
                <p>{apiConnection.message}</p>
                <button type="button" onClick={() => void loadSessions()}>
                  Riprova ora
                </button>
              </section>
            ) : null}
            {bpmnReview ? (
              <BpmnReviewCard
                review={bpmnReview}
                isApproving={isApprovingReview}
                onApprove={approveBpmnReview}
              />
            ) : null}
          </>
        }
      />

      {toastMessage && (
        <div className="toast show" role="status">
          {toastMessage}
        </div>
      )}
    </>
  );
};

function BpmnReviewCard({
  review,
  isApproving,
  onApprove,
}: {
  review: BpmnReview;
  isApproving: boolean;
  onApprove: () => void;
}) {
  const understanding = review.process_understanding || {};
  const actors = understanding.actors || [];
  const decisions = understanding.decisions || [];
  const exceptions = understanding.exceptions || [];
  const dataObjects = understanding.data_objects || [];
  const handoffs = understanding.handoffs || [];
  const alternativePaths = understanding.alternative_paths || [];
  const unknowns = understanding.unknowns || [];
  const qualityReport = review.quality_report || {};
  const semanticModel = review.bpmn_semantic_model || {};
  const lanes = semanticModel.lanes || [];
  const flowNodes = semanticModel.flowNodes || [];
  const semanticWarnings = semanticModel.model_warnings || [];
  const qualityWarnings = [...(qualityReport.blocking_issues || []), ...(qualityReport.warnings || [])].map(
    (item) => item.message
  );

  return (
    <section className="bpmn-review-card" aria-label="Review BPMN pronta">
      <div className="bpmn-review-card-header">
        <div>
          <p className="product-eyebrow">Review BPMN pronta</p>
          <h4>Conferma prima di generare il canvas</h4>
        </div>
        <strong>{review.readiness_score}/10</strong>
      </div>

      <div className="bpmn-review-meter" aria-label={`Readiness ${review.readiness_score} su 10`}>
        <span style={{ width: `${Math.min(100, review.readiness_score * 10)}%` }} />
      </div>

      <pre>{review.bpmn_brief}</pre>

      <div className="bpmn-review-grid">
        <ReviewMiniSection title="Attori/Ruoli" items={actors.map((item) => `${item.label} (${item.kind})`)} />
        <ReviewMiniSection
          title="Lane BPMN"
          items={lanes.map((item) => `${item.name}: ${item.flowNodeRefs?.length || 0} elementi`)}
        />
        <ReviewMiniSection
          title="Elementi BPMN"
          items={flowNodes.map((item) => `${item.type}: ${item.name}`)}
        />
        <ReviewMiniSection
          title="Decisioni"
          items={decisions.map((item) =>
            item.outcomes?.length ? `${item.label}: ${item.outcomes.join(" / ")}` : item.label
          )}
        />
        <ReviewMiniSection
          title="Eccezioni"
          items={exceptions.map((item) =>
            item.handling ? `${item.label}: ${item.handling}` : `${item.label}: da definire`
          )}
        />
        <ReviewMiniSection title="Documenti" items={dataObjects.map((item) => item.label)} />
        <ReviewMiniSection
          title="Handoff"
          items={handoffs.map((item) => item.artifact || item.trigger || "Handoff da precisare")}
        />
        <ReviewMiniSection
          title="Alternative"
          items={alternativePaths.map((item) => (item.is_confirmed === false ? `${item.label}: da confermare` : item.label))}
        />
        <ReviewMiniSection
          title="Qualita"
          items={(qualityReport.dimension_scores || []).map((item) => `${item.dimension}: ${item.score}/10`)}
        />
        <ReviewMiniSection title="Azioni" items={(qualityReport.improvement_actions || []).map((item) => item.action)} />
        <ReviewMiniSection title="Warning" items={semanticWarnings} />
      </div>

      <div className="bpmn-review-missing">
        <span>Informazioni mancanti</span>
        {review.missing_information.length > 0 || unknowns.length > 0 || qualityWarnings.length > 0 ? (
          <ul>
            {review.missing_information.map((item) => (
              <li key={item}>{item}</li>
            ))}
            {unknowns.map((item) => (
              <li key={item.question}>
                {item.question} <strong>{item.severity}</strong>
              </li>
            ))}
            {qualityWarnings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p>Nessuna criticita bloccante indicata.</p>
        )}
      </div>

      <button type="button" disabled={isApproving} onClick={onApprove}>
        {isApproving ? "Genero..." : "Approva e genera BPMN"}
      </button>
    </section>
  );
}

function ReviewMiniSection({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="bpmn-review-mini-section">
      <span>{title}</span>
      {items.length > 0 ? (
        <ul>
          {items.slice(0, 4).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>Non rilevato</p>
      )}
    </div>
  );
}

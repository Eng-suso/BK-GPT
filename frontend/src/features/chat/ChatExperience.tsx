import React, { useEffect, useState } from "react";
import { chatScopeKey, toApiChatScope } from "../../contracts/chat";
import { API_BASE } from "../../lib/api";
import { notifyWorkspaceChanged } from "../../lib/workspaceEvents";
import type { ChatMessage, ChatSession } from "./types";
import type { NavigationTab } from "./navigationTypes";
import type { ChatScope } from "./chatScope";
import { titleForScope } from "./chatScope";
import { ChatShell } from "./ChatShell";

function sessionTitle(message: string): string {
  const clean = message.trim().replace(/\s+/g, " ");
  return clean.length > 28 ? `${clean.slice(0, 28)}...` : clean || "Nuova chat";
}

function normalizeSession(session: any): ChatSession {
  return {
    threadId: session.thread_id || session.threadId,
    title: session.title || "Nuova chat",
    modelName: session.model_name || session.modelName || null,
    createdAt: session.created_at || session.createdAt,
    updatedAt: session.updated_at || session.updatedAt,
    messageCount: session.message_count || (session.messages ? session.messages.length : 0),
    messages: (session.messages || []).map((m: any) => ({
      id: m.id,
      role: m.role as any,
      content: m.content,
      createdAt: m.created_at || m.createdAt,
    })),
  };
}

type ChatExperienceProps = {
  chrome?: "full" | "panel";
  layout?: "standalone" | "embedded";
  scope?: ChatScope;
};

type BpmnReview = {
  bpmn_model_id: string;
  process_id: string;
  source_text: string;
  process_understanding?: ProcessUnderstandingSummary;
  bpmn_semantic_model?: BpmnSemanticModelSummary;
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
  const [isBusy, setIsBusy] = useState(false);
  const [selectedModel, setSelectedModel] = useState("gpt-5.6-luna");
  const [lastUserPrompt, setLastUserPrompt] = useState("");
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [bpmnReview, setBpmnReview] = useState<BpmnReview | null>(null);
  const [isApprovingReview, setIsApprovingReview] = useState(false);

  const activeSession = sessions.find((s) => s.threadId === currentThreadId) || null;
  const messages = activeSession ? activeSession.messages : [];
  const activeTitle = activeSession ? activeSession.title : titleForScope(scope);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 2800);
  };

  const upsertSession = (rawSession: any): ChatSession => {
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

  const loadSessions = async () => {
    try {
      const params = new URLSearchParams({ scope_key: scopeKey });
      const res = await fetch(`${API_BASE}/v1/consultant-chat/sessions?${params}`);
      if (!res.ok) return;
      const data = await res.json();
      const list: ChatSession[] = data.map(normalizeSession);
      setSessions(list);
      if (list.length > 0 && !currentThreadId) {
        setCurrentThreadId(list[0].threadId);
        loadSessionDetail(list[0].threadId);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const loadBpmnReview = async () => {
    if (scope.type !== "canvas") {
      setBpmnReview(null);
      return;
    }

    try {
      const res = await fetch(
        `${API_BASE}/v1/workspace/bpmn-models/${scope.bpmnModelId}/review`,
        { cache: "no-store" }
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
  };

  const loadSessionDetail = async (threadId: string) => {
    try {
      const res = await fetch(`${API_BASE}/v1/consultant-chat/sessions/${threadId}`);
      if (!res.ok) return;
      const data = await res.json();
      upsertSession(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    setSessions([]);
    setCurrentThreadId(null);
    setBpmnReview(null);
    loadSessions();
    loadBpmnReview();
  }, [scopeKey]);

  const createBackendSession = async () => {
    const res = await fetch(`${API_BASE}/v1/consultant-chat/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_name: selectedModel, scope: persistentApiScope }),
    });
    if (!res.ok) throw new Error("Impossible creare la sessione");
    return res.json();
  };

  const transcribeAudio = async (file: File): Promise<string> => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("language", "it");

    const res = await fetch(`${API_BASE}/v1/audio/transcriptions`, {
      method: "POST",
      body: formData,
    });

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

  const sendMessage = async (content: string) => {
    setLastUserPrompt(content);
    const session = await ensureSession(content);

    const userMessage: ChatMessage = { role: "user", content };
    const loadingMessage: ChatMessage = { role: "assistant", content: "Sto elaborando..." };

    setSessions((prev) =>
      prev.map((s) => {
        if (s.threadId !== session.threadId) return s;
        const cleanMsgs = s.messages.filter((m) => m.role !== "error");
        return {
          ...s,
          title: s.title === "Nuova chat" ? sessionTitle(content) : s.title,
          messages: [...cleanMsgs, userMessage, loadingMessage],
        };
      })
    );

    setIsBusy(true);

    try {
      const res = await fetch(
        `${API_BASE}/v1/consultant-chat/sessions/${session.threadId}/messages/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: content,
            model_name: selectedModel,
            scope: apiScope,
          }),
        }
      );

      if (!res.ok || !res.body) throw new Error("Streaming fallito");

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

          if (event.type === "delta") {
            accumulatedText += event.content || "";
            setSessions((prev) =>
              prev.map((s) => {
                if (s.threadId !== session.threadId) return s;
                const msgs = [...s.messages];
                msgs[msgs.length - 1] = { role: "assistant", content: accumulatedText };
                return { ...s, messages: msgs };
              })
            );
          }

          if (event.type === "done") {
            accumulatedText = event.message || accumulatedText;
          }

          if (event.type === "error") {
            throw new Error(event.detail || "Errore backend");
          }
        }
      }

      await loadSessionDetail(session.threadId);
      await loadBpmnReview();
      notifyWorkspaceChanged();
    } catch (err) {
      console.error(err);
      setSessions((prev) =>
        prev.map((s) => {
          if (s.threadId !== session.threadId) return s;
          const msgs = s.messages.slice(0, -1);
          return {
            ...s,
            messages: [
              ...msgs,
              { role: "error", content: "Non sono riuscito a completare questa richiesta." },
            ],
          };
        })
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
        { method: "POST" }
      );

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Nessuna review BPMN pendente da approvare.");
      }

      setBpmnReview(null);
      notifyWorkspaceChanged();
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
            await fetch(`${API_BASE}/v1/consultant-chat/sessions/${id}`, { method: "DELETE" });
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
            await fetch(`${API_BASE}/v1/consultant-chat/sessions?${params}`, { method: "DELETE" });
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
          bpmnReview ? (
            <BpmnReviewCard
              review={bpmnReview}
              isApproving={isApprovingReview}
              onApprove={approveBpmnReview}
            />
          ) : null
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
  const semanticModel = review.bpmn_semantic_model || {};
  const lanes = semanticModel.lanes || [];
  const flowNodes = semanticModel.flowNodes || [];
  const semanticWarnings = semanticModel.model_warnings || [];

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
        <ReviewMiniSection title="Warning" items={semanticWarnings} />
      </div>

      <div className="bpmn-review-missing">
        <span>Informazioni mancanti</span>
        {review.missing_information.length > 0 || unknowns.length > 0 ? (
          <ul>
            {review.missing_information.map((item) => (
              <li key={item}>{item}</li>
            ))}
            {unknowns.map((item) => (
              <li key={item.question}>
                {item.question} <strong>{item.severity}</strong>
              </li>
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

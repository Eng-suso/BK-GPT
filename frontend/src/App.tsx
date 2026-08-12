import React, { useEffect, useState } from "react";
import { ChatMessage, ChatSession } from "./types/chat";
import { NavigationTab } from "./types/navigation";
import { AppShell } from "./components/layout/AppShell";

const API_BASE = (window as any).SUSO_API_BASE || (window.location.protocol === "file:" ? "http://127.0.0.1:8000" : "");

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

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavigationTab>("chat");
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [selectedModel, setSelectedModel] = useState("gpt-5.6-luna");
  const [lastUserPrompt, setLastUserPrompt] = useState("");
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const activeSession = sessions.find((s) => s.threadId === currentThreadId) || null;
  const messages = activeSession ? activeSession.messages : [];
  const activeTitle = activeSession ? activeSession.title : "Suso GPT";

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
      const res = await fetch(`${API_BASE}/v1/consultant-chat/sessions`);
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
    loadSessions();
  }, []);

  const createBackendSession = async () => {
    const res = await fetch(`${API_BASE}/v1/consultant-chat/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_name: selectedModel }),
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
          body: JSON.stringify({ message: content, model_name: selectedModel }),
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

  return (
    <>
      <AppShell
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
            await fetch(`${API_BASE}/v1/consultant-chat/sessions`, { method: "DELETE" });
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
      />

      {toastMessage && (
        <div className="toast show" role="status">
          {toastMessage}
        </div>
      )}
    </>
  );
};

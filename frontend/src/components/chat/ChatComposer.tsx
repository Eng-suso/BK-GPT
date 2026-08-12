import React, { useRef, useState } from "react";
import { ModelSelector } from "./ModelSelector";

interface ChatComposerProps {
  selectedModel?: string;
  isBusy?: boolean;
  onSubmit?: (message: string) => void;
  onAttach?: () => void;
  onVoice?: () => void;
  onModelChange?: (model: string) => void;
}

export const ChatComposer: React.FC<ChatComposerProps> = ({
  selectedModel = "gpt-5.6-luna",
  isBusy = false,
  onSubmit,
  onAttach,
  onVoice,
  onModelChange,
}) => {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const autoGrow = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(160, textareaRef.current.scrollHeight)}px`;
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    autoGrow();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const content = value.trim();
    if (!content || isBusy) return;
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    onSubmit?.(content);
  };

  return (
    <div className="composer-wrap">
      <form className="composer-box" onSubmit={handleSubmit}>
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Scrivi un messaggio..."
          disabled={isBusy}
          autoComplete="off"
        />
        <div className="composer-bottom-bar">
          <ModelSelector selectedModel={selectedModel} onChange={onModelChange} />

          <div className="composer-actions">
            <button
              className="btn-pill-light"
              type="button"
              onClick={() => onAttach?.()}
              title="Allega file"
            >
              <svg viewBox="0 0 24 24">
                <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
              <span>Allega</span>
            </button>
            <button
              className="btn-pill-light"
              type="button"
              onClick={() => onVoice?.()}
              title="Input vocale"
            >
              <svg viewBox="0 0 24 24">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
              <span>Voce</span>
            </button>
            <button
              className="btn-send"
              type="submit"
              disabled={isBusy || !value.trim()}
              title="Invia messaggio"
            >
              <span>Invia</span>
              <svg viewBox="0 0 24 24">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          </div>
        </div>
      </form>
      <div className="footnote">Il modello puo commettere errori. Verifica sempre le risposte importanti.</div>
    </div>
  );
};

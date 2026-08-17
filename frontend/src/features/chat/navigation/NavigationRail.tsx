import React from "react";
import type { NavigationTab } from "../navigationTypes";

interface NavigationRailProps {
  activeTab?: NavigationTab;
  onTabChange?: (tab: NavigationTab) => void;
  onThemeToggle?: () => void;
}

export const NavigationRail: React.FC<NavigationRailProps> = ({
  activeTab = "chat",
  onTabChange,
  onThemeToggle,
}) => {
  return (
    <nav className="rail" aria-label="Navigazione principale">
      <div className="brand-orb" aria-hidden="true" title="Chat" />
      <button
        type="button"
        className={`rail-btn ${activeTab === "chat" ? "active" : ""}`}
        onClick={() => onTabChange?.("chat")}
        title="Chat"
        aria-label="Chat"
      >
        <svg viewBox="0 0 24 24">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </button>
      <button
        type="button"
        className={`rail-btn ${activeTab === "memory" ? "active" : ""}`}
        onClick={() => onTabChange?.("memory")}
        title="Memoria"
        aria-label="Memoria"
      >
        <svg viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 6v6l4 2" />
        </svg>
      </button>
      <button
        type="button"
        className={`rail-btn ${activeTab === "actions" ? "active" : ""}`}
        onClick={() => onTabChange?.("actions")}
        title="Azioni"
        aria-label="Azioni"
      >
        <svg viewBox="0 0 24 24">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      </button>
      <button
        type="button"
        className={`rail-btn ${activeTab === "settings" ? "active" : ""}`}
        onClick={() => onTabChange?.("settings")}
        title="Impostazioni"
        aria-label="Impostazioni"
      >
        <svg viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>
      <div className="rail-spacer" />
      <button
        type="button"
        className="rail-btn"
        onClick={() => onThemeToggle?.()}
        title="Aspetto"
        aria-label="Aspetto"
      >
        <svg viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="5" />
          <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
        </svg>
      </button>
      <div className="status-dot" title="Backend locale collegato" />
    </nav>
  );
};

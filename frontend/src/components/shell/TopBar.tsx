import React from "react";
import { sectionTitles } from "./sections";
import type { ShellSection } from "./types";

type TopBarProps = {
  activeSection: ShellSection;
};

export const TopBar: React.FC<TopBarProps> = ({ activeSection }) => {
  return (
    <header className="product-topbar">
      <div>
        <p className="product-eyebrow">Area lavoro</p>
        <h1>{sectionTitles[activeSection]}</h1>
      </div>
      <div className="product-topbar-actions">
        <button type="button" className="product-action-button">
          Cerca
        </button>
        <button type="button" className="product-avatar" aria-label="Profilo utente">
          MB
        </button>
      </div>
    </header>
  );
};

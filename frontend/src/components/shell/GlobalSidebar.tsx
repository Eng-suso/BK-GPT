import React from "react";
import { shellSections } from "./sections";
import type { ShellSection } from "./types";

type GlobalSidebarProps = {
  activeSection: ShellSection;
  isCollapsed: boolean;
  onSectionChange: (section: ShellSection) => void;
  onToggleCollapsed: () => void;
};

export const GlobalSidebar: React.FC<GlobalSidebarProps> = ({
  activeSection,
  isCollapsed,
  onSectionChange,
  onToggleCollapsed,
}) => {
  return (
    <aside
      className={`product-sidebar${isCollapsed ? " product-sidebar-collapsed" : ""}`}
      aria-label="Navigazione principale"
    >
      <div className="product-brand">
        <div className="product-brand-mark" aria-hidden="true">
          A
        </div>
        <div className="product-brand-copy" aria-hidden={isCollapsed}>
          <strong>Area lavoro</strong>
          <span>Processi</span>
        </div>
      </div>

      <nav className="product-nav" aria-label="Sezioni principali">
        {shellSections.map((item) => {
          const isActive = item.id === activeSection;

          return (
            <button
              key={item.id}
              type="button"
              className={`product-nav-item${isActive ? " product-nav-item-active" : ""}`}
              aria-label={item.label}
              aria-current={isActive ? "page" : undefined}
              onClick={() => onSectionChange(item.id)}
            >
              <span className="product-nav-icon" aria-hidden="true">
                {item.shortLabel}
              </span>
              <span className="product-nav-label" aria-hidden="true">{item.label}</span>
            </button>
          );
        })}
      </nav>

      <button
        type="button"
        className="product-sidebar-toggle"
        aria-label={isCollapsed ? "Espandi navigazione" : "Riduci navigazione"}
        onClick={onToggleCollapsed}
      >
        <span aria-hidden="true">{isCollapsed ? ">" : "<"}</span>
        <span className="product-sidebar-toggle-label">
          {isCollapsed ? "Espandi" : "Riduci"}
        </span>
      </button>
    </aside>
  );
};

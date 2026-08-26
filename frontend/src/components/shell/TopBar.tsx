import React from "react";
import type { ShellSection } from "./types";

type TopBarProps = {
  activeSection: ShellSection;
};

export const TopBar: React.FC<TopBarProps> = () => {
  return (
    <header className="product-topbar">
      <div className="topbar-tenant-select" role="button" tabIndex={0} aria-label="Gruppo selezionato">
        <span className="topbar-tenant-icon" aria-hidden="true">#</span>
        <span>Gruppo DeliR</span>
        <span aria-hidden="true">v</span>
      </div>

      <label className="topbar-search">
        <span aria-hidden="true">S</span>
        <input type="search" placeholder="Cerca processi, KPI, documenti..." />
      </label>

      <div className="topbar-date-range" role="button" tabIndex={0} aria-label="Intervallo date">
        <span aria-hidden="true">[]</span>
        <strong>01 mag 2024 - 31 lug 2024</strong>
        <span aria-hidden="true">v</span>
      </div>

      <div className="product-topbar-actions">
        <button type="button" className="topbar-notification" aria-label="Notifiche">
          <span aria-hidden="true">!</span>
          <strong>3</strong>
        </button>
        <div className="topbar-profile">
          <button type="button" className="product-avatar" aria-label="Profilo utente">
            MB
          </button>
          <div>
            <strong>Marco Bianchi</strong>
            <span>Admin</span>
          </div>
          <span aria-hidden="true">v</span>
        </div>
      </div>
    </header>
  );
};

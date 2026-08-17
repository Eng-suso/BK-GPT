import React from "react";
import { GlobalSidebar } from "./GlobalSidebar";
import { TopBar } from "./TopBar";
import type { ShellSection } from "./types";

type AppShellProps = {
  activeSection: ShellSection;
  onSectionChange: (section: ShellSection) => void;
  children: React.ReactNode;
};

export const AppShell: React.FC<AppShellProps> = ({
  activeSection,
  children,
  onSectionChange,
}) => {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = React.useState(() => {
    return window.localStorage.getItem("workspace-sidebar-collapsed") === "true";
  });

  React.useEffect(() => {
    window.localStorage.setItem("workspace-sidebar-collapsed", String(isSidebarCollapsed));
  }, [isSidebarCollapsed]);

  return (
    <div className={`product-shell${isSidebarCollapsed ? " product-shell-sidebar-collapsed" : ""}`}>
      <GlobalSidebar
        activeSection={activeSection}
        isCollapsed={isSidebarCollapsed}
        onSectionChange={onSectionChange}
        onToggleCollapsed={() => setIsSidebarCollapsed((value) => !value)}
      />
      <div className="product-workspace">
        <TopBar activeSection={activeSection} />
        <main className="product-content">{children}</main>
      </div>
    </div>
  );
};

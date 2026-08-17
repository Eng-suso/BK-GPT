import React from "react";

type StatusTone = "default" | "success" | "warning" | "danger" | "draft";

type StatusBadgeProps = {
  children: React.ReactNode;
  tone?: StatusTone;
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ children, tone = "default" }) => {
  return <span className={`workspace-badge workspace-badge-${tone}`}>{children}</span>;
};

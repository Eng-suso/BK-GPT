import React from "react";

type WorkspaceToolbarProps = {
  searchValue?: string;
  searchPlaceholder?: string;
  onSearchChange?: (value: string) => void;
  children?: React.ReactNode;
};

export const WorkspaceToolbar: React.FC<WorkspaceToolbarProps> = ({
  searchValue,
  searchPlaceholder = "Cerca...",
  onSearchChange,
  children,
}) => {
  return (
    <div className="workspace-toolbar">
      {onSearchChange && (
        <input
          type="search"
          value={searchValue ?? ""}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder={searchPlaceholder}
        />
      )}
      {children}
    </div>
  );
};

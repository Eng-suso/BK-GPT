import React from "react";

type WorkspaceTableProps = {
  columns: string[];
  children: React.ReactNode;
};

export const WorkspaceTable: React.FC<WorkspaceTableProps> = ({ columns, children }) => {
  return (
    <div className="workspace-table-card" tabIndex={0}>
      <table className="workspace-table">
        <thead>
          <tr>
            {columns.map((column, index) => (
              <th key={`${column}-${index}`}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
};

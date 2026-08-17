import React from "react";

type ProgressBarProps = {
  value: number;
  label?: string;
};

export const ProgressBar: React.FC<ProgressBarProps> = ({ value, label }) => {
  const normalizedValue = Math.max(0, Math.min(100, value));

  return (
    <span className="workspace-progress">
      <span className="workspace-progress-track">
        <span style={{ width: `${normalizedValue}%` }} />
      </span>
      {label && <strong>{label}</strong>}
    </span>
  );
};

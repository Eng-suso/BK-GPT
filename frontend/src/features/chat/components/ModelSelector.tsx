import React from "react";

interface ModelSelectorProps {
  selectedModel?: string;
  onChange?: (model: string) => void;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  selectedModel = "gpt-5.6-luna",
  onChange,
}) => {
  return (
    <select
      className="model-select"
      value={selectedModel}
      onChange={(e) => onChange?.(e.target.value)}
      aria-label="Modello AI"
    >
      <option value="gpt-5.6-luna">gpt-5.6-luna</option>
    </select>
  );
};

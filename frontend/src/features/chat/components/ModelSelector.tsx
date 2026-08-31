import React from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/ui/select";

interface ModelSelectorProps {
  selectedModel?: string;
  onChange?: (model: string) => void;
}

const MODELS = ["gpt-5.6-luna"];

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  selectedModel = "gpt-5.6-luna",
  onChange,
}) => {
  // A one-option picker is just noise in an enterprise surface — only show the
  // selector once there is an actual choice to make.
  if (MODELS.length <= 1) return null;

  return (
    <Select value={selectedModel} onValueChange={(value) => onChange?.(value)}>
      <SelectTrigger
        size="sm"
        className="model-select max-w-[160px]"
        aria-label="Modello AI"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {MODELS.map((model) => (
          <SelectItem key={model} value={model}>
            {model}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};

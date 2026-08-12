import React from "react";

interface EmptyStateProps {
  onSelectPrompt?: (prompt: string) => void;
}

export const EmptyState: React.FC<EmptyStateProps> = () => {
  return (
    <div className="welcome">
      <div className="welcome-inner">
        <div className="hero-orb" aria-hidden="true" />
        <h1>Ciao! Come posso aiutarti oggi?</h1>
      </div>
    </div>
  );
};

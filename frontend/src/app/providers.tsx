import React from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { I18nextProvider } from "react-i18next";

import { router } from "@/app/router";
import { ErrorBoundary } from "@/components/feedback";
import { i18n } from "@/lib/i18n";
import { queryClient } from "@/lib/query";

export const AppProviders: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={i18n}>
        {/* La seconda rete, per quello che si rompe sopra le rotte: un
            provider, il router stesso. Dentro la shell c'è già quella che
            tiene in piedi la navigazione. */}
        <ErrorBoundary>
          <RouterProvider router={router} />
        </ErrorBoundary>
      </I18nextProvider>
    </QueryClientProvider>
  );
};
